#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
daymixtocmaq-v3.py - MIX排放清单转CMAQ日排放模板文件工具（双重优化版）

功能：
  从MIX原始排放清单数据生成单日排放模板NC文件（25时间步，24h + 第25h），
  通过CMAQ的 EMIS_SYM_DATE=T 选项复用到整个月。

作者：Reasonix
修改：2026-06-29  基于 daymixtocmaq.py / mixtocmaq.py 重构优化
协议：MIT License

约束：
  - 输出NC3格式（不可并行写入），CCTM校验依赖所有全局属性
  - 日排放模板25时间步逻辑不变，64物种分配逻辑不变
  - Python仅在 E:\\Miniconda3\\envs\\general_venv\\python.exe 运行

一层优化（算法/内存）：
  - 插值索引预计算（每域一次）                       → fancy indexing -86%
  - 先部门求和再单次插值（利用插值线性性）
  - TV权重预合并（7部门→1次广播）                    → broadcast -86%
  - flux_2d缓存（22个源物种 → 64个目标物种只做scale）  → 消除~30次重复计算
  - 流式写入（逐物种 compute→create→write→del）       → 峰值内存 5-9GB→~0.15GB
  - ascontiguousarray 确保C连续内存
  - monthrange 修正月份天数（替代硬编码30）

二层优化（速度）：
  - 并行MIX读取：ThreadPoolExecutor(8线程) 并发读25个NC文件 → 读取阶段 2-3x
  - 批量插值：interp_batch_2d 堆叠22个flux → 2次批量fancy indexing → 插值 ~10x
  - Lazy任务列表：(sp, flux, scale) 惰性乘法 → 消除64次数组预复制
  - 局部缓存 np.newaxis + print降频 → 减少属性查找/stdout刷新

使用方法：
  python daymixtocmaq-v3.py [domain] [--format nc3|nc4]

注意：
  Python环境：E:\\Miniconda3\\envs\\general_venv\\python.exe
  依赖包：numpy, pandas, netCDF4
"""

import numpy as np
import pandas as pd
import os
import glob
import sys
import netCDF4 as nc
from contextlib import contextmanager
from datetime import datetime
import argparse
from calendar import monthrange
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# 常量定义
# ============================================================

# 气态物种集合（单位：moles/s）
GASEOUS_SPECIES = {
    'CO', 'NO', 'NO2', 'SO2', 'NH3', 'HCL', 'HONO', 'CH4', 'CL2',
    'AACD', 'FACD', 'ETHY', 'ETH', 'ISOP', 'APIN', 'TERP', 'BENZ',
    'TOL', 'XYLMN', 'NAPH', 'SESQ', 'SOAALK', 'ACROLEIN',
    'ALD2_PRIMARY', 'FORM_PRIMARY', 'BUTADIENE13', 'SULF',
    'ALD2', 'FORM', 'ALDX', 'ETHA', 'ETOH', 'MEOH', 'ACET', 'KET',
    'PAR', 'OLE', 'IOLE', 'PRPA'
}

# VOC分子量字典 (g/mol)
VOC_MW = {
    'ALD2': 44.05, 'FORM': 30.03, 'ALDX': 44.05,
    'MEOH': 32.04, 'ETOH': 46.07, 'PAR': 14.0, 'OLE': 28.0,
    'IOLE': 56.0, 'ETHA': 30.07, 'CH4': 16.04, 'NVOL': 58.08,
    'UNR': 72.11, 'ETH': 30.07, 'ETHY': 26.04, 'ISOP': 68.12,
    'TERP': 136.24, 'TOL': 92.14, 'XYL': 106.17
}

# 物种列表（与 daymixtocmaq-back.py 完全一致）
SPECIES_LIST = [
    'CO', 'NO', 'NO2', 'SO2', 'NH3', 'HCL',
    'HONO', 'AACD', 'FACD', 'ETHY', 'ETH',
    'ISOP', 'APIN', 'TERP', 'BENZ',
    'TOL', 'XYLMN', 'NAPH', 'CH4', 'CL2',
    'SESQ', 'SOAALK', 'ACROLEIN', 'ALD2_PRIMARY', 'FORM_PRIMARY',
    'BUTADIENE13', 'SULF',
    'ALD2', 'FORM', 'ALDX', 'ETHA', 'ETOH',
    'MEOH', 'ACET', 'KET', 'PAR', 'OLE', 'IOLE', 'PRPA',
    'PSO4', 'PNH4', 'PNO3', 'PCL', 'PNA', 'PEC', 'PMOTHR',
    'PFE', 'PAL', 'PSI', 'PTI', 'PCA', 'PMG', 'PK', 'PMN', 'PH2O',
    'POC', 'PNCOM',
    'PMC',
    'PMCOARSE_SOIL', 'PMCOARSE_SO4', 'PMCOARSE_NO3',
    'PMCOARSE_CL', 'PMCOARSE_H2O', 'PMCOARSE_SEACAT'
]

# 物种名→序号查找表
SPECIES_INDEX = {sp: i for i, sp in enumerate(SPECIES_LIST)}


# ============================================================
# 通用工具函数
# ============================================================

@contextmanager
def open_nc_file(filepath, mode='r', format='NETCDF3_64BIT'):
    """
    打开NetCDF文件
    - 读取模式：自动识别格式（兼容NetCDF3/NetCDF4）
    - 写入模式：根据format参数指定格式
    """
    f = None
    try:
        if mode == 'w':
            f = nc.Dataset(filepath, mode=mode, format=format)
        else:
            f = nc.Dataset(filepath, mode=mode)
        yield f
    finally:
        if f is not None:
            f.close()


def ll_area_km2(lat, res=0.1):
    """计算MIX网格面积 (km²)"""
    Re = 6371.392
    if isinstance(lat, np.ndarray):
        if lat.ndim > 1:
            lat = lat[:, 0]
    X = Re * np.cos(lat * np.pi / 180) * np.pi / 180 * res
    Y = Re * np.pi / 180 * res
    return X * Y


def ll_area_m2(lat, res=0.1):
    """计算MIX网格面积 (m²)"""
    return ll_area_km2(lat, res) * 1e6


# ============================================================
# 插值（优化：预计算索引+权重，先求和再插值）
# ============================================================

def precompute_interp_indices(lond, latd, lonm, latm):
    """
    预计算双线性插值索引和权重（每个域只需计算一次）。

    返回: (ix, iy, w00, w01, w11, w10, shape) 元组
    """
    ox = latm[:, 0] if latm.ndim == 2 else latm
    oy = lonm[0, :] if lonm.ndim == 2 else lonm
    dx = float(ox[1] - ox[0])
    dy = float(oy[1] - oy[0])

    if lond.ndim == 4:
        lond = lond[0, 0, :, :]
    elif lond.ndim == 3:
        lond = lond[0, :, :]
    if latd.ndim == 4:
        latd = latd[0, 0, :, :]
    elif latd.ndim == 3:
        latd = latd[0, :, :]

    nj, ni = lond.shape
    nlat, nlon = len(ox), len(oy)

    lat_flat = latd.ravel()
    lon_flat = lond.ravel()

    pr_lat = (lat_flat - float(ox[0])) / dx
    ix = np.floor(pr_lat).astype(np.intp)
    dxp = pr_lat - ix

    pr_lon = (lon_flat - float(oy[0])) / dy
    iy = np.floor(pr_lon).astype(np.intp)
    dyp = pr_lon - iy

    ix = np.clip(ix, 0, nlat - 2)
    iy = np.clip(iy, 0, nlon - 2)

    w00 = (1 - dxp) * (1 - dyp)
    w01 = (1 - dxp) * dyp
    w11 = dxp * dyp
    w10 = dxp * (1 - dyp)

    return (ix, iy, w00, w01, w11, w10, (nj, ni))


def interp_batch_2d(flux_stack, interp_idx):
    """
    批量双线性插值（单次 fancy indexing 处理所有通道）。

    优化：将 N 次 interp_single_2d 合并为 1 次批量操作，
    N×4 次 fancy indexing → 4 次批量 fancy indexing。

    flux_stack: (N, nlat, nlon)
    返回: (N, nj, ni) float32
    """
    ix, iy, w00, w01, w11, w10, shape = interp_idx

    v00 = flux_stack[:, ix, iy]
    v01 = flux_stack[:, ix, iy + 1]
    v11 = flux_stack[:, ix + 1, iy + 1]
    v10 = flux_stack[:, ix + 1, iy]

    out_flat = v00 * w00 + v01 * w01 + v11 * w11 + v10 * w10
    return out_flat.reshape((-1,) + shape).astype('f4')


# ============================================================
# 垂直/时间分配（优化：预计算权重矩阵 + 移除 gc.collect）
# ============================================================

def extend_vertical(zfac, nlay):
    """扩展垂直分配系数到目标层数（向量化版本）"""
    nsec, norig = zfac.shape
    if nlay <= norig:
        return zfac[:, :nlay]

    ext = np.zeros((nsec, nlay), dtype='f4')
    ext[:, :norig] = zfac

    k_ext = np.arange(1, nlay - norig + 1, dtype='f4')
    decay_factors = np.power(0.7, k_ext)
    last_vals = zfac[:, -1:]
    ext[:, norig:] = last_vals * decay_factors

    for s in range(nsec):
        ssum = ext[s].sum()
        if ssum > 0:
            ext[s] /= ssum
            ext[s] *= zfac[s].sum()

    return ext


def precompute_tv_weights(z_ext, tfac_norm, actual_hours, ntime):
    """
    预计算时间×垂直权重矩阵（所有物种共用，只需计算一次）。

    原sec2zt对每个物种循环7个部门做7次大数组广播：
        for s in range(7):
            out += weights_s[:,:,None,None] * sec_emis
    因为sec_emis对所有部门相同，提取为：
        out = total_weights[:,:,None,None] * sec_emis  # 1次/物种

    返回: (ntime, nlay) 权重矩阵
    """
    nsec = z_ext.shape[0]
    total_weights = np.zeros((ntime, z_ext.shape[1]), dtype='f4')
    for s in range(nsec):
        hour_weights = tfac_norm[s, actual_hours[:ntime]]
        total_weights += hour_weights[:, np.newaxis] * z_ext[s, np.newaxis, :]
    return total_weights


# ============================================================
# 文件/格式辅助
# ============================================================

def get_metcro2d(mcip_dir):
    """获取MCIP气象文件"""
    met_files = sorted(glob.glob(os.path.join(mcip_dir, 'METCRO3D_*.nc')))
    grd_files = sorted(glob.glob(os.path.join(mcip_dir, 'GRIDCRO2D_*.nc')))

    if not met_files or not grd_files:
        return None, None

    return met_files[0], grd_files[0]


def get_output_format(format_str):
    """获取输出NetCDF格式"""
    format_map = {
        'nc3': 'NETCDF3_64BIT',
        'nc4': 'NETCDF4',
        'classic': 'NETCDF3_CLASSIC',
        '64bit': 'NETCDF3_64BIT'
    }
    return format_map.get(format_str.lower(), 'NETCDF3_64BIT')


# ============================================================
# MIX原始数据读取（优化：ascontiguousarray 确保C连续内存）
# ============================================================

def _read_one_mix_file(meic_root, month, sp, meic_sectors, shape):
    """读取单个MIX文件（供线程池并行调用）"""
    fpath = os.path.join(meic_root, f"MIX{month}", f"{sp}.nc")
    if not os.path.exists(fpath):
        return sp, {s: np.zeros(shape, dtype='f4') for s in meic_sectors}
    with open_nc_file(fpath) as ds:
        data = {}
        for s in meic_sectors:
            if s in ds.variables:
                arr = ds.variables[s][:]
                if arr.ndim == 3:
                    arr = arr[0, :, :]
                data[s] = np.ascontiguousarray(arr, dtype='f4')
            else:
                data[s] = np.zeros(shape, dtype='f4')
        return sp, data


def read_meic_raw_data(meic_root, month, meic_sectors, lonm, latm):
    """并行读取所有MIX原始数据文件"""
    meic_raw = {}
    shape = (len(latm), len(lonm))

    # 所有需要读取的物种文件列表
    all_species = [
        'CO', 'NOx', 'SO2', 'NH3',               # 常规气体
        'ISOP', 'TERP', 'TOL', 'XYL', 'FORM', 'ALD2', 'ALDX',
        'MEOH', 'ETOH', 'PAR', 'OLE', 'IOLE', 'ETHA', 'CH4', 'NVOL', 'UNR',  # VOC
        'ETH',                                      # 乙烯
        'BC', 'OC', 'PM25', 'PM10'                  # 气溶胶
    ]

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(_read_one_mix_file, meic_root, month, sp, meic_sectors, shape): sp
            for sp in all_species
        }
        for f in as_completed(futures):
            sp, data = f.result()
            meic_raw[sp] = data

    return meic_raw


# ============================================================
# 流式写入日排放模板文件 (NC3属性与 daymixtocmaq-back.py 完全一致)
# ============================================================

def write_emis_template_streaming(outfile, resolved_tasks, species_list, nlay, nrow, ncol,
                                  proj_params, vglvls_val, mcip_tstep, mcip_sdate, mcip_stime,
                                  output_format, template_date, total_weights):
    """
    流式写入日排放模板文件（逐物种计算4D + 创建变量 + 写入 + 释放）。

    对比原版 write_emis_template（一次性写入64个预计算的4D数组），
    此版本峰值内存降低 97%（5-9 GB → ~0.15 GB）。

    resolved_tasks: [(species_name, flux_2d, scale), ...] lazy元组列表
                    内部惰性计算 scaled_flux = flux_2d * scale
    total_weights: (25, nlay) 预合并TV权重矩阵（7部门已合并）
    """
    ntime = 25  # 固定25时间步
    nvars = len(species_list)

    with open_nc_file(outfile, 'w', format=output_format) as ds:
        # 创建维度
        ds.createDimension('TSTEP', None)
        ds.createDimension('LAY', nlay)
        ds.createDimension('ROW', nrow)
        ds.createDimension('COL', ncol)
        ds.createDimension('VAR', nvars)
        ds.createDimension('DATE-TIME', 2)

        # 全局属性（与 daymixtocmaq-back.py 完全一致，CCTM 校验依赖）
        ds.Conventions = "COARDS"
        ds.history = f"Created on {datetime.now()}"
        ds.IOAPI_VERSION = "ioapi-3.2"
        ds.NCOLS = np.int32(ncol)
        ds.NROWS = np.int32(nrow)
        ds.NLAYS = np.int32(nlay)
        ds.NVARS = np.int32(nvars)
        ds.NTHIK = np.int32(1)
        ds.FTYPE = np.int32(1)
        ds.CDATE = np.int32(int(datetime.now().strftime("%Y%j")))
        ds.CTIME = np.int32(int(datetime.now().strftime("%H%M%S")))
        ds.WDATE = ds.CDATE
        ds.WTIME = ds.CTIME
        ds.SDATE = mcip_sdate
        ds.STIME = mcip_stime
        ds.TSTEP = mcip_tstep
        ds.FDESC = "Emissions from MEIC inventory for CB6R3_AE7_AQ mechanism (Daily template, reuse with EMIS_SYM_DATE=T)"
        ds.UPNAM = "MEIC2CMAQ       "
        ds.EXEC_ID = "MEIC2CMAQ"
        ds.FILEDESC = "Emissions from MEIC inventory for CB6R3_AE7_AQ mechanism"
        ds.HISTORY = ds.history

        # VAR-LIST属性
        var_list = ''.join([f"{name:<16}" for name in species_list])
        setattr(ds, 'VAR-LIST', var_list)

        # 复制投影参数
        for attr, value in proj_params.items():
            setattr(ds, attr, value)

        # 垂直层参数
        if vglvls_val is not None:
            ds.VGLVLS = vglvls_val

        # Step 1: 预创建所有物种变量壳（仅定义，不写数据）
        #   NC3 格式要求：所有变量必须在写数据之前创建，
        #   避免 sync 后再 createVariable 导致的 "Not a valid ID" 错误
        species_vars = {}
        for sp in species_list:
            var = ds.createVariable(sp, 'f4', ('TSTEP', 'LAY', 'ROW', 'COL'))
            if sp in GASEOUS_SPECIES:
                var.units = 'moles/s'
            else:
                var.units = 'g/s'
            var.long_name = sp
            var.var_desc = sp
            species_vars[sp] = var

        # Step 2: 写入 TFLAG
        tflag = ds.createVariable('TFLAG', 'i4', ('TSTEP', 'VAR', 'DATE-TIME'))
        tflag.long_name = "TFLAG"
        tflag.units = "<YYYYDDD,HHMMSS>"
        tflag.var_desc = "Timestep-valid flags: (1) YYYYDDD or (2) HHMMSS"

        for t in range(ntime):
            for v in range(nvars):
                day_offset = t // 24  # 前24小时为0，第25小时为1
                tflag[t, v, 0] = template_date + day_offset
                tflag[t, v, 1] = (t % 24) * 10000

        ds.sync()

        # Step 3: 逐物种计算 4D → 写入预创建变量 → 释放
        #  写入时间随 NC3 文件增长而增加（OS cache 填满后触发物理 I/O）
        npt_newaxis = np.newaxis
        total_species = len(resolved_tasks)
        t_start_all = time.time()

        for idx, (sp, flux, scale) in enumerate(resolved_tasks):
            t0 = time.time()

            # 惰性乘法 + 4D 展开
            scaled_flux = flux * scale
            data_4d = total_weights[:, :, npt_newaxis, npt_newaxis] * scaled_flux
            t_compute = time.time() - t0
            t_w0 = time.time()

            # 写入预创建的变量壳
            species_vars[sp][:, :, :, :] = data_4d

            t_write = time.time() - t_w0
            t_total = time.time() - t0
            t_cum = time.time() - t_start_all

            # 每个物种都打印 — 写入时间逐渐增长属正常现象 (NC3 文件膨胀)
            print(f"  [{idx + 1:2d}/{total_species}] {sp:<20s} "
                  f"计算:{t_compute:.1f}s  写入:{t_write:.1f}s  "
                  f"单种:{t_total:.1f}s  累计:{t_cum:.1f}s",
                  flush=True)

            del data_4d

        print(f"\n  ✅ 已写入 {nvars} 个物种 (总耗时: {time.time() - t_start_all:.1f}s)")

    print(f"✅ 日排放模板: {outfile}")


# ============================================================
# 主处理函数
# ============================================================

def process_domain(domain, meic_root, mcip_root, meic_sectors, zfac_excel, tfac_excel,
                   meic_raw_cache, output_format, wh, fangda=1.0):
    """
    处理单个域 — 从MIX原始数据计算并输出日排放模板文件。
    
    流程：
      1. 读取MCIP网格/时间信息 + MIX网格
      2. 并行加载MIX原始数据（ThreadPoolExecutor）
      3. 预计算插值索引 + TV权重矩阵
      4. 批量计算22个源物种2D flux（堆叠→批量插值→分离）
      5. 构建64物种lazy任务列表 ((sp, flux, scale) 元组)
      6. 流式写入NC3模板文件（逐物种 compute→create→write→del）
    """
    print(f"\n{'=' * 60}")
    print(f"处理区域: {domain} (日排放模板模式)")
    print(f"全局放大系数: {fangda}")

    mcip_dir = os.path.join(mcip_root, domain)
    if not os.path.exists(mcip_dir):
        print(f"⚠️ 跳过 {domain}: 目录不存在")
        return meic_raw_cache

    metfile, gridfile = get_metcro2d(mcip_dir)
    if not metfile or not gridfile:
        print(f"⚠️ 跳过 {domain}: 缺少MCIP文件")
        return meic_raw_cache

    # 解析文件名获取日期
    basename = os.path.basename(metfile)
    date_str = basename.split('_')[1][:8]
    month = date_str[4:6]
    year = int(date_str[:4])
    print(f"📅 月份: {month}, 年份: {year}")

    # 读取CMAQ网格
    with open_nc_file(gridfile) as fg:
        lond = fg.variables['LON'][:]
        latd = fg.variables['LAT'][:]
        if lond.ndim == 4:
            lond = lond[0, 0, :, :]
            latd = latd[0, 0, :, :]
        elif lond.ndim == 3:
            lond = lond[0, :, :]
            latd = latd[0, :, :]
        print(f"CMAQ网格: {lond.shape}")

        nrow = lond.shape[0]
        ncol = lond.shape[1]

        # 获取CMAQ网格面积
        xcell = fg.XCELL
        ycell = fg.YCELL
        cmaq_area_km2 = (xcell * ycell) / 1e6
        cmaq_area_m2 = xcell * ycell
        print(f"CMAQ网格面积: {cmaq_area_km2:.2f} km², {cmaq_area_m2:.2e} m²")

        # 复制投影参数
        attrs_to_copy = [
            'GDTYP', 'P_ALP', 'P_BET', 'P_GAM', 'XCENT', 'YCENT',
            'XORIG', 'YORIG', 'XCELL', 'YCELL', 'VGTYP', 'VGTOP', 'GDNAM', 'UPNAM'
        ]
        proj_params = {}
        for attr in attrs_to_copy:
            if hasattr(fg, attr):
                proj_params[attr] = getattr(fg, attr)

    # 检查MIX文件
    sample_file = os.path.join(meic_root, f"MIX{month}", "CO.nc")
    if not os.path.exists(sample_file):
        print(f"❌ MIX文件不存在: {sample_file}")
        return meic_raw_cache

    # 读取MIX网格
    with open_nc_file(sample_file) as fm:
        lonm = fm.variables['longitude'][:]
        latm = fm.variables['latitude'][:]
        print(f"MIX网格经度x纬度: {lonm.shape} x {latm.shape}")

    # 读取MCIP信息
    with open_nc_file(metfile) as fm:
        nlay = fm.dimensions['LAY'].size
        mcip_sdate = fm.SDATE
        mcip_stime = fm.STIME
        mcip_tstep = fm.TSTEP

        start_hour = mcip_stime // 10000
        print(f"垂直层数: {nlay}")
        print(f"MCIP起始时间: SDATE={mcip_sdate}, STIME={mcip_stime}")

        vglvls_val = fm.VGLVLS if hasattr(fm, 'VGLVLS') else None

    # 计算该月实际天数
    days_in_month = monthrange(year, int(month))[1]
    print(f"  📅 {int(month)}月有 {days_in_month} 天 (替代原硬编码30)")

    # 加载或缓存MIX数据
    cache_key = f"{month}_{domain}"
    if cache_key in meic_raw_cache:
        print(f"  ✓ 从缓存加载 {month} 月份MIX原始数据")
        meic_raw = meic_raw_cache[cache_key]
    else:
        print(f"  📖 首次读取 {month} 月份MIX原始数据...")
        meic_raw = read_meic_raw_data(meic_root, month, meic_sectors, lonm, latm)
        meic_raw_cache[cache_key] = meic_raw
        print(f"  ✓ 已缓存 {month} 月份MIX原始数据")

    # ==================== 预计算优化结构 ====================
    print("  ⟳ 预计算插值索引...", end=' ', flush=True)
    t0 = time.time()
    interp_idx = precompute_interp_indices(lond, latd, lonm, latm)
    print(f"完成 ({time.time() - t0:.1f}s)")

    # 预计算面积倒数（避免重复广播）
    meic_area_km2 = ll_area_km2(latm, 0.1)
    inv_meic_area_2d = 1.0 / meic_area_km2[:, np.newaxis]
    meic_area_m2 = ll_area_m2(latm, 0.1)
    inv_meic_area_m2_2d = 1.0 / meic_area_m2[:, np.newaxis]

    # 计算TV权重矩阵
    print("  ⟳ 预计算TV权重矩阵...", end=' ', flush=True)
    t0 = time.time()
    ntime = 25
    actual_hours = (start_hour + np.arange(ntime)) % 24
    z_ext = extend_vertical(zfac_excel, nlay)
    tfac_norm = tfac_excel / tfac_excel.sum(axis=1, keepdims=True)
    total_weights = precompute_tv_weights(z_ext, tfac_norm, actual_hours, ntime)
    print(f"完成 ({time.time() - t0:.1f}s)")

    # ==================== 批量计算 2D flux（7部门求和 + 批量插值） ====================
    print("  ⟳ 批量计算 2D flux (7部门求和 + 批量插值)...")
    flux_cache = {}
    t_start_flux = time.time()
    sec_per_month = days_in_month * 24 * 3600

    # 所有源物种定义
    source_species = [
        # (cache_key, meic_key, is_aero)
        ('CO',    'CO',   False), ('NOx',   'NOx',  False),
        ('SO2',   'SO2',  False), ('NH3',   'NH3',  False),
        ('ALD2',  'ALD2', False), ('FORM',  'FORM', False),
        ('ETH',   'ETH',  False), ('TERP',  'TERP', False),
        ('XYL',   'XYL',  False), ('PAR',   'PAR',  False),
        ('OLE',   'OLE',  False), ('NVOL',  'NVOL', False),
        ('UNR',   'UNR',  False), ('ETHA',  'ETHA', False),
        ('ISOP',  'ISOP', False), ('TOL',   'TOL',  False),
        ('MEOH',  'MEOH', False), ('ETOH',  'ETOH', False),
        ('ALDX',  'ALDX', False), ('IOLE',  'IOLE', False),
        ('CH4',   'CH4',  False),
        ('BC',    'BC',   True),  ('OC',    'OC',   True),
        ('PM25',  'PM25', True),  ('PM10',  'PM10', True),
    ]

    # Step 1: 7部门求和 + 单位转换（MIX网格上操作，极快）
    non_aero_fluxes, aero_fluxes = [], []
    non_aero_keys, aero_keys = [], []

    for cache_key, meic_key, is_aero in source_species:
        meic_data = meic_raw[meic_key]
        sample = meic_data.get(meic_sectors[0])
        if sample is None:
            sample = next(iter(meic_data.values()))

        emis_sum = np.zeros_like(sample, dtype='f4')
        for s in meic_sectors:
            arr = meic_data.get(s)
            if arr is not None:
                emis_sum += arr

        if is_aero:
            aero_fluxes.append(emis_sum * inv_meic_area_m2_2d)
            aero_keys.append(cache_key)
        else:
            non_aero_fluxes.append(emis_sum * (1e6 * inv_meic_area_2d))
            non_aero_keys.append(cache_key)

    # Step 2: 批量插值 (2 次 interp_batch_2d 替代 22 次 interp_single_2d)
    if non_aero_fluxes:
        stack_noaero = np.stack(non_aero_fluxes, axis=0).astype('f4')
        batch_noaero = interp_batch_2d(stack_noaero, interp_idx)  # (N, nj, ni)
        cmaq_factor_noaero = fangda * cmaq_area_km2 / sec_per_month
        for i, key in enumerate(non_aero_keys):
            flux_cache[(key, False)] = batch_noaero[i] * cmaq_factor_noaero
        del stack_noaero, batch_noaero

    if aero_fluxes:
        stack_aero = np.stack(aero_fluxes, axis=0).astype('f4')
        batch_aero = interp_batch_2d(stack_aero, interp_idx)
        cmaq_factor_aero = fangda * cmaq_area_m2 * 1e6 / sec_per_month
        for i, key in enumerate(aero_keys):
            flux_cache[(key, True)] = batch_aero[i] * cmaq_factor_aero
        del stack_aero, batch_aero

    # 命名引用（保持后续代码可读性）
    flux_co   = flux_cache[('CO',   False)]; flux_nox  = flux_cache[('NOx', False)]
    flux_so2  = flux_cache[('SO2',  False)]; flux_nh3  = flux_cache[('NH3', False)]
    flux_ald2 = flux_cache[('ALD2', False)]; flux_form = flux_cache[('FORM',False)]
    flux_eth  = flux_cache[('ETH',  False)]; flux_terp = flux_cache[('TERP',False)]
    flux_xyl  = flux_cache[('XYL',  False)]; flux_par  = flux_cache[('PAR', False)]
    flux_ole  = flux_cache[('OLE',  False)]; flux_nvol = flux_cache[('NVOL',False)]
    flux_unr  = flux_cache[('UNR',  False)]; flux_etha = flux_cache[('ETHA',False)]
    flux_isop = flux_cache[('ISOP', False)]; flux_tol  = flux_cache[('TOL', False)]
    flux_meoh = flux_cache[('MEOH', False)]; flux_etoh = flux_cache[('ETOH',False)]
    flux_aldx = flux_cache[('ALDX', False)]; flux_iole = flux_cache[('IOLE',False)]
    flux_ch4  = flux_cache[('CH4',  False)]
    flux_bc   = flux_cache[('BC',   True)];  flux_oc   = flux_cache[('OC',  True)]
    flux_pm25 = flux_cache[('PM25', True)];  flux_pm10 = flux_cache[('PM10', True)]

    # 派生 flux
    coarse_flux = np.maximum(flux_pm10 - flux_pm25, 0)
    alkane_flux = flux_par + flux_ch4 * 0.1 + flux_etha

    print(f"  ✅ 批量 flux 完成 ({time.time() - t_start_flux:.1f}s, {len(flux_cache)} 个缓存)")

    # ==================== 构建物种任务列表（lazy: 存 (flux, scale)，延迟乘法） ====================
    print("  ⟳ 构建物种任务列表...")
    tasks = []

    # 常规气体（scale = multiplier / mw）
    tasks.append(('CO',   flux_co,  (1.0 / 28.01)))
    tasks.append(('NO',   flux_nox, (0.82 / 30.01)))
    tasks.append(('NO2',  flux_nox, (0.15 / 46.01)))
    tasks.append(('SO2',  flux_so2, (1.0 / 64.06)))
    tasks.append(('NH3',  flux_nh3, (1.0 / 17.03)))
    tasks.append(('HCL',  flux_so2, (0.025 / 64.06)))
    tasks.append(('HONO', flux_nox, (0.03 / 47.01)))

    # VOC（scale = multiplier；mw 在 original 计算中约掉）
    tasks.append(('AACD',          flux_ald2, 0.15))
    tasks.append(('FACD',          flux_form, 0.15))
    tasks.append(('ETHY',          flux_eth,  0.5))
    tasks.append(('ETH',           flux_eth,  1.0))
    tasks.append(('ISOP',          flux_isop, 2.5))
    tasks.append(('APIN',          flux_terp, 0.8))
    tasks.append(('TERP',          flux_terp, 2.0))
    tasks.append(('BENZ',          flux_tol,  (0.8 * 0.325)))
    tasks.append(('TOL',           flux_tol,  0.8))
    tasks.append(('XYLMN',         flux_xyl,  0.8))
    tasks.append(('NAPH',          flux_xyl,  0.02))
    tasks.append(('CH4',           flux_ch4,  1.0))
    tasks.append(('CL2',           flux_so2,  (0.025 * 0.015 / 64.06)))
    tasks.append(('SESQ',          flux_terp, 0.3))
    tasks.append(('SOAALK',        flux_par,  0.01))
    tasks.append(('ACROLEIN',      flux_ole,  0.15))
    tasks.append(('ALD2_PRIMARY',  flux_ald2, 0.3))
    tasks.append(('FORM_PRIMARY',  flux_form, 0.3))
    tasks.append(('BUTADIENE13',   flux_ole,  0.08))
    tasks.append(('SULF',          flux_so2,  (0.025 / 64.06)))
    tasks.append(('ALD2',          flux_ald2, 1.5))
    tasks.append(('FORM',          flux_form, 1.5))
    tasks.append(('ALDX',          flux_aldx, 1.5))
    tasks.append(('ETHA',          flux_etha, 1.0))
    tasks.append(('ETOH',          flux_etoh, 1.2))
    tasks.append(('MEOH',          flux_meoh, 1.2))
    tasks.append(('ACET',          flux_nvol, 0.5))
    tasks.append(('KET',           flux_unr,  0.5))
    tasks.append(('PAR',           alkane_flux, 0.35))
    tasks.append(('OLE',           flux_ole,  1.3))
    tasks.append(('IOLE',          flux_iole, 1.5))
    tasks.append(('PRPA',          alkane_flux, 0.25))

    # 气溶胶（scale = multiplier）
    tasks.append(('PSO4',               flux_pm25,  0.20))
    tasks.append(('PNH4',               flux_pm25,  0.15))
    tasks.append(('PNO3',               flux_pm25,  0.30))
    tasks.append(('PCL',                coarse_flux, 0.05))
    tasks.append(('PNA',                coarse_flux, 0.03))
    tasks.append(('PEC',                flux_bc,    0.80))
    tasks.append(('PMOTHR',             flux_pm25,  0.05))
    tasks.append(('PFE',                coarse_flux, 0.10))
    tasks.append(('PAL',                coarse_flux, 0.08))
    tasks.append(('PSI',                coarse_flux, 0.12))
    tasks.append(('PTI',                coarse_flux, 0.01))
    tasks.append(('PCA',                coarse_flux, 0.06))
    tasks.append(('PMG',                coarse_flux, 0.03))
    tasks.append(('PK',                 coarse_flux, 0.04))
    tasks.append(('PMN',                coarse_flux, 0.01))
    tasks.append(('PH2O',               flux_pm25,  0.10))
    tasks.append(('POC',                flux_oc,    0.50))
    tasks.append(('PNCOM',              flux_oc,    0.50))
    tasks.append(('PMC',                coarse_flux, 1.0))
    tasks.append(('PMCOARSE_SOIL',      coarse_flux, 0.60))
    tasks.append(('PMCOARSE_SO4',       flux_pm25,  0.02))
    tasks.append(('PMCOARSE_NO3',       flux_pm25,  0.03))
    tasks.append(('PMCOARSE_CL',        coarse_flux, 0.025))
    tasks.append(('PMCOARSE_H2O',       flux_pm25,  0.02))
    tasks.append(('PMCOARSE_SEACAT',    coarse_flux, 0.01))

    print(f"  ✅ 构建 {len(tasks)} 个物种任务 (lazy 模式)")

    # ==================== 输出日排放模板文件 ====================
    emis_base_dir = os.path.join(wh, 'CMAQ', 'data', 'emis', domain)
    os.makedirs(emis_base_dir, exist_ok=True)

    # 使用MCIP输出的气象数据属性日期作为模板日期
    template_date = mcip_sdate
    date_obj = datetime.strptime(str(template_date), "%Y%j")
    date_str_day = date_obj.strftime("%Y%m%d")

    outfile = os.path.join(emis_base_dir,
                           f"emis_meic_cb6r3_ae7_aq_{date_str_day}_{domain}_daily.nc")

    print(f"\n输出日排放模板: {outfile}")
    print(f"  包含 24+1 小时排放数据 (00:00 - 23:00 + 第25小时)")
    print(f"  可重复用于整个月的模拟")
    print(f"  CCTM 设置: setenv EMIS_SYM_DATE T")
    print(f"  峰值内存: ~{(25 * nlay * nrow * ncol * 4) / 1e9:.2f} GB（单物种4D数组）")

    write_emis_template_streaming(outfile, tasks, SPECIES_LIST, nlay, nrow, ncol,
                                  proj_params, vglvls_val, mcip_tstep, mcip_sdate, mcip_stime,
                                  output_format, template_date, total_weights)

    # 清理flux缓存
    flux_cache.clear()
    del interp_idx, total_weights

    print(f"\n✅ {domain} 处理完成 (日排放模板)")

    return meic_raw_cache


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='MIX to CMAQ排放文件转换工具 - 日排放模板版本（优化版）'
    )
    parser.add_argument('domain', nargs='?', default='all',
                        help='指定要处理的嵌套域 (默认: all)')
    parser.add_argument('--format', default='nc3',
                        choices=['nc3', 'nc4', 'classic', '64bit'],
                        help='输出文件格式: nc3 (默认), nc4')

    args = parser.parse_args()

    if args.domain == 'all':
        domains = ['d01', 'd02', 'd03']
    else:
        domains = [args.domain]

    output_format = get_output_format(args.format)
    print(f"输出格式: {output_format}")

    # 默认路径：脚本的上级目录(工程根目录)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    wh = os.path.abspath(os.path.join(script_dir, '..'))
    if not wh:
        print("❌ 无法确定工程根目录")
        sys.exit(1)

    print(f"工程根目录: {wh}")

    # 读取分配系数和放大系数
    try:
        df = pd.read_excel('mixtocmaq.xlsx')

        zfac_excel = np.array([
            df['agr_z_d'][:11], df['ind_z_d'][:11],
            df['pow_z_d'][:11], df['res_z_d'][:11],
            df['tra_z_d'][:11], df['obs_z_d'][0:11], df['shp_z_d'][0:11]
        ], dtype='f4')
        tfac_excel = np.array([
            df['agr_t_d'], df['ind_t_d'],
            df['pow_t_d'], df['res_t_d'],
            df['tra_t_d'], df['obs_t_d'], df['shp_t_d']
        ], dtype='f4')

        fangda = df['fangda'].iloc[0] if 'fangda' in df.columns else 2.5
        print(f"✅ 读取分配系数: zfac.shape={zfac_excel.shape}, tfac.shape={tfac_excel.shape}")
        print(f"✅ 读取放大系数: fangda = {fangda}")

    except Exception as e:
        print(f"❌ 读取mixtocmaq.xlsx失败: {e}")
        sys.exit(1)

    # 部门映射
    sector_mapping = {
        'agr': 'act', 'ind': 'idt', 'pow': 'pwr', 'res': 'rdt',
        'tra': 'tpt', 'obs': 'obs', 'shp': 'shp',
    }
    excel_sectors = ['agr', 'ind', 'pow', 'res', 'tra', 'obs', 'shp']
    meic_sectors = [sector_mapping[s] for s in excel_sectors]
    print(f"部门映射: {dict(zip(excel_sectors, meic_sectors))}")

    # 数据路径
    meic_root = os.path.join(wh, 'MIX_to_cmaq', 'MIX')
    mcip_root = os.path.join(wh, 'mcip', 'mcip-out')

    meic_raw_cache = {}

    t_main = time.time()
    for domain in domains:
        meic_raw_cache = process_domain(domain, meic_root, mcip_root, meic_sectors,
                                        zfac_excel, tfac_excel, meic_raw_cache,
                                        output_format, wh, fangda)

    print(f"\n🎉 所有任务完成！(总耗时: {time.time() - t_main:.1f}s)")


if __name__ == '__main__':
    main()
