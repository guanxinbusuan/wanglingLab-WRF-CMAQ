import numpy as np
import pandas as pd
import os
import glob
import sys
import netCDF4 as nc
from contextlib import contextmanager
from datetime import datetime
import gc
import argparse
from calendar import monthrange


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
    X = Re * np.cos(lat * np.pi/180) * np.pi/180 * res
    Y = Re * np.pi/180 * res
    return X * Y


def ll_area_m2(lat, res=0.1):
    """计算MIX网格面积 (m²)"""
    return ll_area_km2(lat, res) * 1e6


def meic2cmaq(lon_inp, lat_inp, lon_meic, lat_meic, emis):
    """双线性插值：将MIX数据插值到CMAQ网格（向量化版本）"""
     # 如果输入是 2D 网格 
    if lat_meic.ndim == 2:
        ox = lat_meic[:, 0]  # 取一列作为纬度轴 
        oy = lon_meic[0, :]  # 取一行作为经度轴 
    else:
        ox = lat_meic
        oy = lon_meic
    # 强制转换为 float，避免 numpy.ma 对象带来的 __float__ 转换错误
    dx = float(ox[1] - ox[0])
    dy = float(oy[1] - oy[0])


    if lon_inp.ndim == 4:
        lon_inp = lon_inp[0, 0, :, :]
    elif lon_inp.ndim == 3:
        lon_inp = lon_inp[0, :, :]
    
    if lat_inp.ndim == 4:
        lat_inp = lat_inp[0, 0, :, :]
    elif lat_inp.ndim == 3:
        lat_inp = lat_inp[0, :, :]
    
    nj, ni = lon_inp.shape
    nlat = len(ox)
    nlon = len(oy)
    
    # --- 向量化 std：一次性计算所有格点的索引和权重 ---
    # 展平为1D便于批量计算，最后 reshape 回 (nj, ni)
    lat_flat = lat_inp.ravel()
    lon_flat = lon_inp.ravel()
    N = len(lat_flat)
    
    # 计算归一化坐标和小数部分（全部数组操作）
    pr_lat = (lat_flat - float(ox[0])) / dx
    ix = np.floor(pr_lat).astype(np.intp)
    dxp = pr_lat - ix          # 小数偏移量
    
    pr_lon = (lon_flat - float(oy[0])) / dy
    iy = np.floor(pr_lon).astype(np.intp)
    dyp = pr_lon - iy          # 小数偏移量
    
    # 边界裁剪（等价于原版 std 中的 min/max 边界保护）
    ix = np.clip(ix, 0, nlat - 2)
    iy = np.clip(iy, 0, nlon - 2)
    
    # --- 向量化 inp：批量双线性插值 ---
    # 使用 fancy indexing 一次取出四个角点的值
    v00 = emis[ix, iy]           # 左下角
    v01 = emis[ix, iy + 1]       # 左上角
    v11 = emis[ix + 1, iy + 1]   # 右上角
    v10 = emis[ix + 1, iy]       # 右下角
    
    # 双线性权重组合（与原版 inp 完全一致的数学公式）
    out_flat = (v00 * (1 - dxp) * (1 - dyp) +
                v01 * (1 - dxp) * dyp +
                v11 * dxp * dyp +
                v10 * dxp * (1 - dyp))
    
    return out_flat.reshape(nj, ni).astype('f4')


def extend_vertical(zfac, nlay):
    """扩展垂直分配系数到目标层数（向量化版本）"""
    nsec, norig = zfac.shape
    if nlay <= norig:
        return zfac[:, :nlay]
    
    ext = np.zeros((nsec, nlay), dtype='f4')
    ext[:, :norig] = zfac
    

    # 预计算所有扩展层的衰减因子：[0.7^1, 0.7^2, ..., 0.7^(nlay-norig)]
    k_ext = np.arange(1, nlay - norig + 1, dtype='f4')
    decay_factors = np.power(0.7, k_ext)   # shape: (nlay - norig,)
    
    # 对每个部门批量填充扩展层（向量化）
    last_vals = zfac[:, -1:]                  
    ext[:, norig:] = last_vals * decay_factors  
    
    # 归一化每个部门（保持原版逻辑不变）
    for s in range(nsec):
        ssum = ext[s].sum()
        if ssum > 0:
            ext[s] /= ssum
            ext[s] *= zfac[s].sum()
    
    return ext


def sec2zt(sec_emis, zfac, tfac, nlay, ntime_out, start_hour=0):
    """时间和垂直分配（向量化版本）"""
    import gc
    gc.collect()
    
    nsec = zfac.shape[0]
    nhrs_in = tfac.shape[1]
    nj, ni = sec_emis.shape
    
    # 归一化时间分配系数
    tfac_norm = tfac / tfac.sum(axis=1, keepdims=True)
    
    # 扩展垂直分配系数
    z = extend_vertical(zfac, nlay)
    
    out = np.zeros((ntime_out, nlay, nj, ni), dtype='f4')
    

    # 预计算所有时间步的实际小时索引
    actual_hours = (start_hour + np.arange(ntime_out)) % nhrs_in   # shape: (ntime_out,)
    
    for s in range(nsec):
        # 提取该部门各时间步的小时权重：shape (ntime_out,)
        hour_weights = tfac_norm[s, actual_hours]
        
        # 外积：(ntime_out,) × (nlay,) → (ntime_out, nlay)，即完整时空权重矩阵
        weights = hour_weights[:, np.newaxis] * z[s, np.newaxis, :]
        
        # 广播乘法：(ntime_out, nlay, 1, 1) * (1, 1, nj, ni) → (ntime_out, nlay, nj, ni)
        out += weights[:, :, np.newaxis, np.newaxis] * sec_emis
    
    return out


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


def read_meic_raw_data(meic_root, month, meic_sectors, lonm, latm):
    """读取MIX原始数据"""
    meic_raw = {}
    
    # 常规气体物种（单位：吨/月）
    gas_species = ['CO', 'NOx', 'SO2', 'NH3']
    for sp in gas_species:
        fpath = os.path.join(meic_root, f"MIX{month}", f"{sp}.nc")
        if os.path.exists(fpath):
            with open_nc_file(fpath) as ds:
                meic_raw[sp] = {}
                for s in meic_sectors:
                    if s in ds.variables:
                        arr = ds.variables[s][:]
                        if arr.ndim == 3:
                            arr = arr[0, :, :]
                        meic_raw[sp][s] = arr.astype('f4')
                    else:
                        meic_raw[sp][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
        else:
            print(f"  ⚠️ {sp}.nc 不存在")
            meic_raw[sp] = {}
            for s in meic_sectors:
                meic_raw[sp][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
    
    # VOC物种（单位：百万摩尔/月）
    voc_species = ['ISOP', 'TERP', 'TOL', 'XYL', 'FORM', 'ALD2', 'ALDX',
                   'MEOH', 'ETOH', 'PAR', 'OLE', 'IOLE', 'ETHA', 'CH4', 'NVOL', 'UNR']
    for sp in voc_species:
        fpath = os.path.join(meic_root, f"MIX{month}", f"{sp}.nc")
        if os.path.exists(fpath):
            with open_nc_file(fpath) as ds:
                meic_raw[sp] = {}
                for s in meic_sectors:
                    if s in ds.variables:
                        arr = ds.variables[s][:]
                        if arr.ndim == 3:
                            arr = arr[0, :, :]
                        meic_raw[sp][s] = arr.astype('f4')
                    else:
                        meic_raw[sp][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
        else:
            print(f"  ⚠️ {sp}.nc 不存在，使用零值")
            meic_raw[sp] = {}
            for s in meic_sectors:
                meic_raw[sp][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
    
    # 乙烯单独处理（单位：百万摩尔/月）
    fpath = os.path.join(meic_root, f"MIX{month}", "ETH.nc")
    if os.path.exists(fpath):
        with open_nc_file(fpath) as ds:
            meic_raw['ETH'] = {}
            for s in meic_sectors:
                if s in ds.variables:
                    arr = ds.variables[s][:]
                    if arr.ndim == 3:
                        arr = arr[0, :, :]
                    meic_raw['ETH'][s] = arr.astype('f4')
                else:
                    meic_raw['ETH'][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
    else:
        print(f"  ⚠️ ETH.nc 不存在，使用零值")
        meic_raw['ETH'] = {}
        for s in meic_sectors:
            meic_raw['ETH'][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
    
    # 气溶胶物种（单位：吨/月）
    aero_species = ['BC', 'OC', 'PM25', 'PM10']
    for sp in aero_species:
        fpath = os.path.join(meic_root, f"MIX{month}", f"{sp}.nc")
        if os.path.exists(fpath):
            with open_nc_file(fpath) as ds:
                meic_raw[sp] = {}
                for s in meic_sectors:
                    if s in ds.variables:
                        arr = ds.variables[s][:]
                        if arr.ndim == 3:
                            arr = arr[0, :, :]
                        meic_raw[sp][s] = arr.astype('f4')
                    else:
                        meic_raw[sp][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
        else:
            print(f"  ⚠️ {sp}.nc 不存在")
            meic_raw[sp] = {}
            for s in meic_sectors:
                meic_raw[sp][s] = np.zeros((len(latm), len(lonm)), dtype='f4')
    
    return meic_raw


def interpolate_and_allocate(meic_data, meic_sectors, lonm, latm, lond, latd, 
                              zfac, tfac, nlay, ntime_out, start_hour,
                              cmaq_area_km2, cmaq_area_m2,
                              is_gas=False, is_voc=False, molecular_weight=46.01,
                              fangda=1.0):
    """
    插值 + 时间/垂直分配，输出总排放速率
    """
    meic_area_km2 = ll_area_km2(latm, 0.1)
    meic_area_2d = meic_area_km2[:, np.newaxis]
    meic_area_m2 = ll_area_m2(latm, 0.1)
    meic_area_m2_2d = meic_area_m2[:, np.newaxis]
    
    sector_emissions = []
    for s in meic_sectors:
        arr = meic_data.get(s, np.zeros((len(latm), len(lonm)), dtype='f4'))
        
        if is_gas:
            g_per_month = arr * 1e6
            g_per_km2_month = g_per_month / meic_area_2d
            idw = meic2cmaq(lond, latd, lonm, latm, g_per_km2_month)
            sector_emissions.append(idw)
        elif is_voc:
            g_per_month = arr * 1e6 * molecular_weight
            g_per_km2_month = g_per_month / meic_area_2d
            idw = meic2cmaq(lond, latd, lonm, latm, g_per_km2_month)
            sector_emissions.append(idw)
        else:
            ton_per_m2_month = arr / meic_area_m2_2d
            idw = meic2cmaq(lond, latd, lonm, latm, ton_per_m2_month)
            sector_emissions.append(idw)
    
    monthly_flux = np.sum(sector_emissions, axis=0)
    
    # 转换为小时通量
    if is_gas or is_voc:
        hourly_flux = monthly_flux / (30 * 24)
        total_per_hour = hourly_flux * cmaq_area_km2
        total_per_sec = total_per_hour / 3600
        total_per_sec = total_per_sec / molecular_weight
    else:
        hourly_flux = monthly_flux / (30 * 24)
        hourly_flux = hourly_flux * 1e6
        total_per_hour = hourly_flux * cmaq_area_m2
        total_per_sec = total_per_hour / 3600
    
    total_per_sec = total_per_sec * fangda
    
    return sec2zt(total_per_sec, zfac, tfac, nlay, ntime_out, start_hour)


def write_emis_template(outfile, species_data, species_list, nlay, nrow, ncol,
                        proj_params, vglvls_val, mcip_tstep, mcip_sdate, mcip_stime,
                        output_format, template_date):
    """
    写入日排放模板文件
    """
    ntime = 25  # 固定25小时
    nvars = len(species_list)
    
    # 气态物种集合
    GASEOUS_SPECIES = {
        'CO', 'NO', 'NO2', 'SO2', 'NH3', 'HCL', 'HONO', 'CH4', 'CL2',
        'AACD', 'FACD', 'ETHY', 'ETH', 'ISOP', 'APIN', 'TERP', 'BENZ',
        'TOL', 'XYLMN', 'NAPH', 'SESQ', 'SOAALK', 'ACROLEIN',
        'ALD2_PRIMARY', 'FORM_PRIMARY', 'BUTADIENE13', 'SULF',
        'ALD2', 'FORM', 'ALDX', 'ETHA', 'ETOH', 'MEOH', 'ACET', 'KET',
        'PAR', 'OLE', 'IOLE', 'PRPA'
    }
    
    with open_nc_file(outfile, 'w', format=output_format) as ds:
        # 创建维度
        ds.createDimension('TSTEP', None)
        ds.createDimension('LAY', nlay)
        ds.createDimension('ROW', nrow)
        ds.createDimension('COL', ncol)
        ds.createDimension('VAR', nvars)
        ds.createDimension('DATE-TIME', 2)
        
        # 全局属性
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
        
        # 创建TFLAG变量（所有时间步使用同一天期）
        tflag = ds.createVariable('TFLAG', 'i4', ('TSTEP', 'VAR', 'DATE-TIME'))
        tflag.long_name = "TFLAG"
        tflag.units = "<YYYYDDD,HHMMSS>"
        tflag.var_desc = "Timestep-valid flags: (1) YYYYDDD or (2) HHMMSS"
        
        for t in range(ntime):
            for v in range(nvars):
                # 儒略日：第25小时自动 +1 天
                day_offset = t // 24  # 前24小时为0，第25小时为1
                tflag[t, v, 0] = template_date + day_offset
                # 小时：0, 10000, 20000... 230000, 0
                tflag[t, v, 1] = (t % 24) * 10000
                        
        ds.sync()
        
        # 写入每个物种
        total_species = len(species_list)
        for idx, (sp, data) in enumerate(zip(species_list, species_data)):
            print(f"  [{idx+1}/{total_species}] 写入物种: {sp}...", end=' ', flush=True)
            var = ds.createVariable(sp, 'f4', ('TSTEP', 'LAY', 'ROW', 'COL'))
            
            # 确保数据维度正确
            if data.shape[0] != ntime:
                if data.shape[0] < ntime:
                    last_slice = data[-1:, :, :, :]
                    n_repeat = ntime - data.shape[0]
                    data = np.concatenate([data, np.repeat(last_slice, n_repeat, axis=0)], axis=0)
                else:
                    data = data[:ntime, :, :, :]
            
            if sp in GASEOUS_SPECIES:
                var.units = 'moles/s'
            else:
                var.units = 'g/s'
            
            var.long_name = sp
            var.var_desc = sp
            if data.dtype != np.dtype('f4'):
                print("还不是 f4 数据结构,直接写,需转换float32")
                data = data.astype('f4')
            
            print("已经是 float32 数据结构,直接写,零拷贝节省NC3格式不压缩的高内存占用")
            var[:] = data   #如果已经是 float32，直接写，零拷贝
            print("✓", flush=True)
        
        print(f"  ✅ 已写入 {nvars} 个物种")
    
    print(f"✅ 日排放模板: {outfile}")


def process_domain(domain, meic_root, mcip_root, meic_sectors, zfac_excel, tfac_excel, 
                   meic_raw_cache, output_format,wh,fangda=1.0):
    """处理单个域 - 输出日排放模板文件"""
    print(f"\n{'='*60}")
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
    print(f"📅 月份: {month}")
    
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
    
    print("  ⟳ 计算 24 小时排放模板...")
    
    # ==================== 计算一天的数据（24小时） ====================
    day_ntime = 25
    
    def compute_day_alloc(meic_data, is_gas=False, is_voc=False, molecular_weight=46.01, multiplier=1.0):
        result = interpolate_and_allocate(meic_data, meic_sectors, lonm, latm, 
                                           lond, latd, zfac_excel, tfac_excel, 
                                           nlay, day_ntime, start_hour,
                                           cmaq_area_km2, cmaq_area_m2,
                                           is_gas=is_gas, is_voc=is_voc, 
                                           molecular_weight=molecular_weight,
                                           fangda=fangda)
        return result * multiplier
    
    # VOC 分子量字典
    VOC_MW = {
        'ALD2': 44.05, 'FORM': 30.03, 'ALDX': 44.05,
        'MEOH': 32.04, 'ETOH': 46.07, 'PAR': 14.0, 'OLE': 28.0,
        'IOLE': 56.0, 'ETHA': 30.07, 'CH4': 16.04, 'NVOL': 58.08,
        'UNR': 72.11, 'ETH': 30.07, 'ETHY': 26.04, 'ISOP': 68.12,
        'TERP': 136.24, 'TOL': 92.14, 'XYL': 106.17
    }
    
    # 常规气体
    co_day = compute_day_alloc(meic_raw['CO'], is_gas=True, molecular_weight=28.01)
    no_day = compute_day_alloc(meic_raw['NOx'], is_gas=True, molecular_weight=30.01, multiplier=0.82)
    no2_day = compute_day_alloc(meic_raw['NOx'], is_gas=True, molecular_weight=46.01, multiplier=0.15)
    so2_day = compute_day_alloc(meic_raw['SO2'], is_gas=True, molecular_weight=64.06)
    nh3_day = compute_day_alloc(meic_raw['NH3'], is_gas=True, molecular_weight=17.03)
    hcl_day = so2_day * 0.025
    hono_day = compute_day_alloc(meic_raw['NOx'], is_gas=True, molecular_weight=47.01, multiplier=0.03)
    
    # VOC 物种
    ald2_raw = meic_raw['ALD2']
    form_raw = meic_raw['FORM']
    eth_raw = meic_raw['ETH']
    terp_raw = meic_raw['TERP']
    xyl_raw = meic_raw['XYL']
    par_raw = meic_raw['PAR']
    ole_raw = meic_raw['OLE']
    nvol_raw = meic_raw['NVOL']
    unr_raw = meic_raw['UNR']
    etha_raw = meic_raw['ETHA']
    
    aacd_day = compute_day_alloc(ald2_raw, is_voc=True, molecular_weight=VOC_MW['ALD2'], multiplier=0.15)
    facd_day = compute_day_alloc(form_raw, is_voc=True, molecular_weight=VOC_MW['FORM'], multiplier=0.15)
    ethy_day = compute_day_alloc(eth_raw, is_voc=True, molecular_weight=VOC_MW['ETHY'], multiplier=0.5)
    eth_day = compute_day_alloc(eth_raw, is_voc=True, molecular_weight=VOC_MW['ETH'])
    apin_day = compute_day_alloc(terp_raw, is_voc=True, molecular_weight=VOC_MW['TERP'], multiplier=0.8)
    naph_day = compute_day_alloc(xyl_raw, is_voc=True, molecular_weight=VOC_MW['XYL'], multiplier=0.02)
    ch4_day = compute_day_alloc(meic_raw['CH4'], is_voc=True, molecular_weight=VOC_MW['CH4'])
    cl2_day = hcl_day * 0.015
    sesq_day = compute_day_alloc(terp_raw, is_voc=True, molecular_weight=VOC_MW['TERP'], multiplier=0.3)
    soaalk_day = compute_day_alloc(par_raw, is_voc=True, molecular_weight=VOC_MW['PAR'], multiplier=0.01)
    acrolein_day = compute_day_alloc(ole_raw, is_voc=True, molecular_weight=VOC_MW['OLE'], multiplier=0.15)
    ald2_primary_day = compute_day_alloc(ald2_raw, is_voc=True, molecular_weight=VOC_MW['ALD2'], multiplier=0.3)
    form_primary_day = compute_day_alloc(form_raw, is_voc=True, molecular_weight=VOC_MW['FORM'], multiplier=0.3)
    butadiene13_day = compute_day_alloc(ole_raw, is_voc=True, molecular_weight=VOC_MW['OLE'], multiplier=0.08)
    sulf_day = so2_day * 0.025
    
    # 烷烃重新分配
    par_voc = compute_day_alloc(par_raw, is_voc=True, molecular_weight=VOC_MW['PAR'])
    etha_voc = compute_day_alloc(etha_raw, is_voc=True, molecular_weight=VOC_MW['ETHA'])
    total_alkane = par_voc + ch4_day * 0.1 + etha_voc
    par_day = total_alkane * 0.35
    prpa_day = total_alkane * 0.25
    etha_day = etha_voc
    
    ole_day = compute_day_alloc(ole_raw, is_voc=True, molecular_weight=VOC_MW['OLE'], multiplier=1.3)
    iole_day = compute_day_alloc(meic_raw['IOLE'], is_voc=True, molecular_weight=VOC_MW['IOLE'], multiplier=1.5)
    
    tol_day = compute_day_alloc(meic_raw['TOL'], is_voc=True, molecular_weight=VOC_MW['TOL'], multiplier=0.8)
    xylmn_day = compute_day_alloc(xyl_raw, is_voc=True, molecular_weight=VOC_MW['XYL'], multiplier=0.8)
    benz_day = tol_day * 0.325
    
    isop_day = compute_day_alloc(meic_raw['ISOP'], is_voc=True, molecular_weight=VOC_MW['ISOP'], multiplier=2.5)
    terp_day = compute_day_alloc(terp_raw, is_voc=True, molecular_weight=VOC_MW['TERP'], multiplier=2.0)
    
    form_day = compute_day_alloc(form_raw, is_voc=True, molecular_weight=VOC_MW['FORM'], multiplier=1.5)
    ald2_day = compute_day_alloc(ald2_raw, is_voc=True, molecular_weight=VOC_MW['ALD2'], multiplier=1.5)
    aldx_day = compute_day_alloc(meic_raw['ALDX'], is_voc=True, molecular_weight=VOC_MW['ALDX'], multiplier=1.5)
    meoh_day = compute_day_alloc(meic_raw['MEOH'], is_voc=True, molecular_weight=VOC_MW['MEOH'], multiplier=1.2)
    etoh_day = compute_day_alloc(meic_raw['ETOH'], is_voc=True, molecular_weight=VOC_MW['ETOH'], multiplier=1.2)
    acet_day = compute_day_alloc(nvol_raw, is_voc=True, molecular_weight=VOC_MW['NVOL'], multiplier=0.5)
    ket_day = compute_day_alloc(unr_raw, is_voc=True, molecular_weight=VOC_MW['UNR'], multiplier=0.5)
    
    # 气溶胶
    bc_day = compute_day_alloc(meic_raw['BC'], is_gas=False)
    oc_day = compute_day_alloc(meic_raw['OC'], is_gas=False)
    pm25_day = compute_day_alloc(meic_raw['PM25'], is_gas=False)
    pm10_day = compute_day_alloc(meic_raw['PM10'], is_gas=False)
    coarse_day = np.maximum(pm10_day - pm25_day, 0)
    
    # 精细颗粒物分配
    pso4_day = pm25_day * 0.20
    pnh4_day = pm25_day * 0.15
    pno3_day = pm25_day * 0.30
    pcl_day = coarse_day * 0.05
    pna_day = coarse_day * 0.03
    pec_day = bc_day * 0.80
    pmothr_day = pm25_day * 0.05
    pfe_day = coarse_day * 0.10
    pal_day = coarse_day * 0.08
    psi_day = coarse_day * 0.12
    pti_day = coarse_day * 0.01
    pca_day = coarse_day * 0.06
    pmg_day = coarse_day * 0.03
    pk_day = coarse_day * 0.04
    pmn_day = coarse_day * 0.01
    ph2o_day = pm25_day * 0.10
    poc_day = oc_day * 0.50
    pncom_day = oc_day * 0.50
    
    # 粗颗粒物
    pmc_day = coarse_day.copy()
    pmcoarse_soil_day = coarse_day * 0.60
    pmcoarse_so4_day = pso4_day * 0.10
    pmcoarse_no3_day = pno3_day * 0.10
    pmcoarse_cl_day = pcl_day * 0.50
    pmcoarse_h2o_day = ph2o_day * 0.20
    pmcoarse_seacat_day = coarse_day * 0.01
    
    # 物种列表和数据
    species_list = [
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
    
    species_day_data = [
        co_day, no_day, no2_day, so2_day, nh3_day, hcl_day,
        hono_day, aacd_day, facd_day, ethy_day, eth_day,
        isop_day, apin_day, terp_day, benz_day,
        tol_day, xylmn_day, naph_day, ch4_day, cl2_day,
        sesq_day, soaalk_day, acrolein_day, ald2_primary_day, form_primary_day,
        butadiene13_day, sulf_day,
        ald2_day, form_day, aldx_day, etha_day, etoh_day,
        meoh_day, acet_day, ket_day, par_day, ole_day, iole_day, prpa_day,
        pso4_day, pnh4_day, pno3_day, pcl_day, pna_day, pec_day, pmothr_day,
        pfe_day, pal_day, psi_day, pti_day, pca_day, pmg_day, pk_day, pmn_day, ph2o_day,
        poc_day, pncom_day,
        pmc_day,
        pmcoarse_soil_day, pmcoarse_so4_day, pmcoarse_no3_day,
        pmcoarse_cl_day, pmcoarse_h2o_day, pmcoarse_seacat_day
    ]
    
    # ==================== 输出日排放模板文件 ====================
    emis_base_dir = os.path.join(wh, 'CMAQ', 'data', 'emis', domain)
    os.makedirs(emis_base_dir, exist_ok=True)
    
    # 使用MCIP输出的气象数据的属性日期作为模板日期
    template_date = mcip_sdate  # 应该是气象日期
    date_obj = datetime.strptime(str(template_date), "%Y%j")
    date_str_day = date_obj.strftime("%Y%m%d")
    
    outfile = os.path.join(emis_base_dir, f"emis_meic_cb6r3_ae7_aq_{date_str_day}_{domain}_daily.nc")
    
    print(f"\n输出日排放模板: {outfile}")
    print(f"  包含 24 小时排放数据 (00:00 - 23:00)")
    print(f"  可重复用于整个月的模拟")
    print(f"  CCTM 设置: setenv EMIS_SYM_DATE T")
    
    write_emis_template(outfile, species_day_data, species_list, nlay, nrow, ncol,
                        proj_params, vglvls_val, mcip_tstep, mcip_sdate, mcip_stime,
                        output_format, template_date)
    
    print(f"\n✅ {domain} 处理完成 (日排放模板)")
    
    return meic_raw_cache


def main():
    parser = argparse.ArgumentParser(description='MIX to CMAQ排放文件转换工具 - 输出日排放模板')
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
    
    # 默认路径：脚本daymixtocmaq.py的上级目录(工程根目录)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_projecthome = os.path.abspath(os.path.join(script_dir, '..'))
    # 优先使用我设定好的默认路径（工程根路径）
    wh = default_projecthome
    if not wh:
        print("❌ 请设置 WRFHOME 环境变量")
        sys.exit(1)
    
    # 读取分配系数和放大系数
    try:
        df = pd.read_excel('mixtocmaq.xlsx')
        
        zfac_excel = np.array([df['agr_z_d'][:11], df['ind_z_d'][:11], 
                               df['pow_z_d'][:11], df['res_z_d'][:11], 
                               df['tra_z_d'][:11],df['obs_z_d'][0:11],df['shp_z_d'][0:11]], dtype='f4')
        tfac_excel = np.array([df['agr_t_d'], df['ind_t_d'], 
                               df['pow_t_d'], df['res_t_d'], 
                               df['tra_t_d'],df['obs_t_d'],df['shp_t_d']], dtype='f4')
        
        fangda = df['fangda'].iloc[0] if 'fangda' in df.columns else 2.5
        print(f"✅ 读取分配系数: zfac.shape={zfac_excel.shape}, tfac.shape={tfac_excel.shape}")
        print(f"✅ 读取放大系数: fangda = {fangda}")
        
    except Exception as e:
        print(f"❌ 读取mixtocmaq.xlsx失败: {e}")
        sys.exit(1)
    
    # 部门映射
    sector_mapping = {
        'agr': 'act', 'ind': 'idt', 'pow': 'pwr', 'res': 'rdt', 'tra': 'tpt','obs':'obs','shp':'shp',
    }
    excel_sectors = ['agr', 'ind', 'pow', 'res', 'tra','obs','shp']
    meic_sectors = [sector_mapping[s] for s in excel_sectors]
    print(f"部门映射: {dict(zip(excel_sectors, meic_sectors))}")
    
    # 数据路径
    meic_root = os.path.join(wh, 'MIX_to_cmaq/MIX')
    mcip_root = os.path.join(wh, 'mcip/mcip-out')
    
    meic_raw_cache = {}
    
    for domain in domains:
        meic_raw_cache = process_domain(domain, meic_root, mcip_root, meic_sectors, 
                                         zfac_excel, tfac_excel, meic_raw_cache, 
                                         output_format, wh,fangda)
    
    print("\n🎉 所有任务完成！")


if __name__ == '__main__':
    main()
