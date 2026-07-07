"""
WRF-Chem 的 wrfbiochemi 文件转换为 CMAQ v5.3.2 BEIS 3.61 标准的 B3GRD 文件
严格按照 SMOKE 官方模板格式
"""

import numpy as np
import netCDF4 as nc
import sys
import os
import glob
import re
from datetime import datetime

# 默认路径：脚本daymixtocmaq.py的上级目录(工程根目录)
script_dir = os.path.dirname(os.path.abspath(__file__))
default_projecthome = os.path.abspath(os.path.join(script_dir, '..'))
# 优先使用我设定好的默认路径（工程根路径）
wh = default_projecthome

#wh = os.environ.get('WRFHOME')
#if not wh:
#    print("❌ 请设置 WRFHOME 环境变量")
#    sys.exit(1)

WRFBIOCHEMI_DIR = os.path.join(wh, "wrfbiochemi_to_cmaq")
MCIP_DIR = os.path.join(wh, "mcip/mcip-out")
B3GRD_OUTPUT_DIR = os.path.join(wh, "CMAQ/data/land")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__))

# 土壤 NO 基准值（g N/km²/h）
SOIL_NO_BASE = {
    1: 15.0, 2: 15.0, 3: 20.0, 4: 20.0, 5: 18.0,
    6: 25.0, 7: 25.0, 8: 35.0, 9: 35.0, 10: 30.0,
    11: 10.0, 12: 100.0, 13: 5.0, 14: 80.0, 15: 0.0,
    16: 0.0, 17: 0.0, 20: 5.0
}

MONTH_NAMES = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
               'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

# 模板中的完整变量列表（共77个）
TEMPLATE_VARS = [
    'AVG_ISOPS', 'AVG_MBOS', 'AVG_METHS', 'AVG_APINS', 'AVG_BPINS',
    'AVG_D3CARS', 'AVG_DLIMS', 'AVG_CAMPHS', 'AVG_MYRCS', 'AVG_ATERPS',
    'AVG_BPHES', 'AVG_SABIS', 'AVG_PCYMS', 'AVG_OCIMS', 'AVG_ATHUS',
    'AVG_TRPOS', 'AVG_GTERPS', 'AVG_ETHES', 'AVG_PROPES', 'AVG_ETHOS',
    'AVG_ACETS', 'AVG_HEXAS', 'AVG_HEXES', 'AVG_HEXYS', 'AVG_FORMS',
    'AVG_ACTALS', 'AVG_BUTES', 'AVG_ETHAS', 'AVG_FORACS', 'AVG_ACTACS',
    'AVG_BUTOS', 'AVG_COS', 'AVG_ORVOCS', 'AVG_SESQTS',
    'LAI_ISOPS', 'LAI_MBOS', 'LAI_METHS',
    'AVG_ISOPW', 'AVG_MBOW', 'AVG_METHW', 'AVG_APINW', 'AVG_BPINW',
    'AVG_D3CARW', 'AVG_DLIMW', 'AVG_CAMPHW', 'AVG_MYRCW', 'AVG_ATERPW',
    'AVG_BPHEW', 'AVG_SABIW', 'AVG_PCYMW', 'AVG_OCIMW', 'AVG_ATHUW',
    'AVG_TRPOW', 'AVG_GTERPW', 'AVG_ETHEW', 'AVG_PROPEW', 'AVG_ETHOW',
    'AVG_ACETW', 'AVG_HEXAW', 'AVG_HEXEW', 'AVG_HEXYW', 'AVG_FORMW',
    'AVG_ACTALW', 'AVG_BUTEW', 'AVG_ETHAW', 'AVG_FORACW', 'AVG_ACTACW',
    'AVG_BUTOW', 'AVG_COW', 'AVG_ORVOCW', 'AVG_SESQTW',
    'LAI_ISOPW', 'LAI_MBOW', 'LAI_METHW',
    'AVG_NOAG_GROW', 'AVG_NOAG_NONGROW', 'AVG_NONONAG'
]

# 物种比例系数（相对于 ISOP）
SPECIES_RATIOS = {
    'AVG_ISOP': 1.0,
    'AVG_MBO': 0.08,
    'AVG_METH': 0.15,
    'AVG_APIN': 0.15,
    'AVG_BPIN': 0.10,
    'AVG_D3CAR': 0.02,
    'AVG_DLIM': 0.08,
    'AVG_CAMPH': 0.03,
    'AVG_MYRC': 0.05,
    'AVG_ATERP': 0.05,
    'AVG_BPHE': 0.02,
    'AVG_SABI': 0.03,
    'AVG_PCYM': 0.02,
    'AVG_OCIM': 0.04,
    'AVG_ATHU': 0.02,
    'AVG_TRPO': 0.02,
    'AVG_GTERP': 0.04,
    'AVG_ETHE': 0.02,
    'AVG_PROPE': 0.02,
    'AVG_ETHO': 0.02,
    'AVG_ACET': 0.08,
    'AVG_HEXA': 0.02,
    'AVG_HEXE': 0.02,
    'AVG_HEXY': 0.02,
    'AVG_FORM': 0.05,
    'AVG_ACTAL': 0.02,
    'AVG_BUTE': 0.02,
    'AVG_ETHA': 0.02,
    'AVG_FORAC': 0.02,
    'AVG_ACTAC': 0.02,
    'AVG_BUTO': 0.02,
    'AVG_COS': 0.01,
    'AVG_ORVOC': 0.02,
    'AVG_SESQT': 0.02,
    'AVG_OVOC': 0.5,
    'AVG_CO': 0.01,
}

# 碳质量（g C/mol）
C_MASS = {
    'AVG_ISOP': 60.05,
    'AVG_MBO': 60.05,
    'AVG_METH': 12.01,
    'AVG_APIN': 120.10,
    'AVG_BPIN': 120.10,
    'AVG_D3CAR': 120.10,
    'AVG_DLIM': 120.10,
    'AVG_CAMPH': 120.10,
    'AVG_MYRC': 120.10,
    'AVG_ATERP': 120.10,
    'AVG_BPHE': 120.10,
    'AVG_SABI': 120.10,
    'AVG_PCYM': 120.10,
    'AVG_OCIM': 120.10,
    'AVG_ATHU': 120.10,
    'AVG_TRPO': 120.10,
    'AVG_GTERP': 120.10,
    'AVG_ETHE': 24.02,
    'AVG_PROPE': 36.03,
    'AVG_ETHO': 24.02,
    'AVG_ACET': 36.03,
    'AVG_HEXA': 72.12,
    'AVG_HEXE': 72.12,
    'AVG_HEXY': 72.12,
    'AVG_FORM': 12.01,
    'AVG_ACTAL': 24.02,
    'AVG_BUTE': 48.04,
    'AVG_ETHA': 24.02,
    'AVG_FORAC': 24.02,
    'AVG_ACTAC': 24.02,
    'AVG_BUTO': 48.04,
    'AVG_COS': 12.01,
    'AVG_ORVOC': 60.0,
    'AVG_SESQT': 180.15,
    'AVG_OVOC': 48.0,
    'AVG_CO': 12.01,
}


def find_mcip_files(domain):
    mcip_domain_dir = os.path.join(MCIP_DIR, domain)
    if not os.path.isdir(mcip_domain_dir):
        raise FileNotFoundError(f"MCIP 目录不存在: {mcip_domain_dir}")
    grid_files = sorted(glob.glob(os.path.join(mcip_domain_dir, "GRIDCRO2D*.nc")))
    lufrac_files = sorted(glob.glob(os.path.join(mcip_domain_dir, "LUFRAC_CRO*.nc")))
    met_files = sorted(glob.glob(os.path.join(mcip_domain_dir, "METCRO3D*.nc")))
    if not grid_files:
        raise FileNotFoundError(f"未找到 GRIDCRO2D 文件")
    if not lufrac_files:
        raise FileNotFoundError(f"未找到 LUFRAC_CRO 文件")
    if not met_files:
        met_files = sorted(glob.glob(os.path.join(mcip_domain_dir, "METBDY3D*.nc")))
        if not met_files:
            raise FileNotFoundError(f"未找到气象文件")
    return grid_files[0], lufrac_files[0], met_files[0]


def find_wrfbiochemi_file(domain):
    search_patterns = [f"wrfbiochemi_{domain}", f"wrfbiochemi_{domain}_*", f"wrfbiochemi.*{domain}*", "wrfbiochemi*"]
    for pat in search_patterns:
        files = glob.glob(os.path.join(WRFBIOCHEMI_DIR, pat))
        if files:
            return sorted(files)[0]
    raise FileNotFoundError(f"在 {WRFBIOCHEMI_DIR} 未找到 wrfbiochemi 文件")


def extract_date_from_filename(filename):
    match = re.search(r'(\d{8})', os.path.basename(filename))
    if not match:
        return datetime.now().strftime("%Y%m%d")
    return match.group(1)


def get_grid_info_from_mcip(grid_file):
    with nc.Dataset(grid_file, 'r') as fg:
        nrow = len(fg.dimensions['ROW'])
        ncol = len(fg.dimensions['COL'])
        required = ['XCELL', 'YCELL', 'XORIG', 'YORIG', 'XCENT', 'YCENT',
                    'P_ALP', 'P_BET', 'P_GAM', 'GDTYP']
        grid = {'nrow': nrow, 'ncol': ncol}
        for attr in required:
            if not hasattr(fg, attr):
                raise AttributeError(f"GRIDCRO2D 缺失必需属性: {attr}")
            grid[attr.lower()] = getattr(fg, attr)
    return grid


def get_landuse_from_lufrac(lufrac_file):
    with nc.Dataset(lufrac_file, 'r') as lf:
        lufrac = lf.variables['LUFRAC'][0]
        landuse = np.argmax(lufrac, axis=0) + 1
    return landuse


def get_soil_no_from_landuse(landuse_data):
    soil_no = np.zeros_like(landuse_data, dtype=np.float32)
    for code, val in SOIL_NO_BASE.items():
        soil_no[landuse_data == code] = val
    soil_no[soil_no == 0] = 10.0
    return soil_no


def get_wrf_dimensions(wrf_ds):
    return (len(wrf_ds.dimensions['south_north']), len(wrf_ds.dimensions['west_east']))


def calculate_crop_indices(wrf_nrow, wrf_ncol, cmaq_nrow, cmaq_ncol):
    if wrf_nrow < cmaq_nrow or wrf_ncol < cmaq_ncol:
        raise ValueError("WRF网格小于CMAQ网格，无法裁剪")
    r_start = (wrf_nrow - cmaq_nrow) // 2
    r_end = r_start + cmaq_nrow
    c_start = (wrf_ncol - cmaq_ncol) // 2
    c_end = c_start + cmaq_ncol
    return r_start, r_end, c_start, c_end


def get_wrf_emission_factors(wrf_ds, r_start, r_end, c_start, c_end):
    isop = wrf_ds.variables['MSEBIO_ISOP'][0, r_start:r_end, c_start:c_end]
    isop = np.nan_to_num(isop, 0.0)
    if 'MSEBIO_MONO' in wrf_ds.variables:
        mono = wrf_ds.variables['MSEBIO_MONO'][0, r_start:r_end, c_start:c_end]
        mono = np.nan_to_num(mono, 0.0)
    else:
        mono = isop * 0.3
    if 'MSEBIO_OVOC' in wrf_ds.variables:
        ovoc = wrf_ds.variables['MSEBIO_OVOC'][0, r_start:r_end, c_start:c_end]
        ovoc = np.nan_to_num(ovoc, 0.0)
    else:
        ovoc = isop * 0.5
    return isop, mono, ovoc


def get_lai_data(wrf_ds, month, r_start, r_end, c_start, c_end):
    month_idx = max(0, min(11, month - 1))
    lai = wrf_ds.variables['MLAI'][0, month_idx, r_start:r_end, c_start:c_end]
    return np.nan_to_num(lai, 0.0)


def calculate_emissions(ef_isop, ef_mono, ef_ovoc, soil_no_base, lai, grid_area, season="summer"):
    """计算BEIS标准排放（单位：gramsC/hour）"""
    results = {}
    
    # 首先计算基础 ISOP 排放（单位：gramsC/hour）
    # 修正：不乘 grid_area（B3GRD 需要单位面积排放强度）
    isop_base = ef_isop * C_MASS['AVG_ISOP'] / 1e6
    
    # 为每个物种计算排放
    for var_name in TEMPLATE_VARS:
        # 跳过 LAI 和土壤 NO 变量（稍后处理）
        if var_name.startswith('LAI_'):
            continue
        if var_name in ['AVG_NOAG_GROW', 'AVG_NOAG_NONGROW', 'AVG_NONONAG']:
            continue
            
        # 提取基础物种名（去掉 S/W 后缀）
        base_name = var_name[:-1] if var_name.endswith(('S', 'W')) else var_name
        
        if base_name in SPECIES_RATIOS:
            ratio = SPECIES_RATIOS[base_name]
            c_mass = C_MASS.get(base_name, 12.01)
            results[var_name] = isop_base * ratio * (c_mass / C_MASS['AVG_ISOP'])
        else:
            results[var_name] = np.zeros_like(lai)
    
    # 添加 LAI 变量
    for lai_var in ['LAI_ISOPS', 'LAI_MBOS', 'LAI_METHS', 'LAI_ISOPW', 'LAI_MBOW', 'LAI_METHW']:
        results[lai_var] = lai
    
    # 添加土壤 NO 变量
    if season == "summer":
        no_factor = 1.0
    else:
        no_factor = 0.3
    
    # 修正：不乘 grid_area（B3GRD 需要单位面积排放强度）
    results['AVG_NOAG_GROW'] = soil_no_base * no_factor * 0.005
    results['AVG_NOAG_NONGROW'] = soil_no_base * no_factor * 0.002
    results['AVG_NONONAG'] = soil_no_base * no_factor * 0.003
    
    return results


def write_b3grd_file(out_path, grid, summer, winter, domain, date_str):
    """严格按照官方模板格式写入B3GRD文件"""
    
    nvars = len(TEMPLATE_VARS)
    
    ds = nc.Dataset(out_path, 'w', format='NETCDF3_64BIT')
    
    # 维度（严格按照模板）
    ds.createDimension('TSTEP', 1)
    ds.createDimension('DATE-TIME', 2)
    ds.createDimension('LAY', 1)
    ds.createDimension('VAR', nvars)
    ds.createDimension('ROW', grid['nrow'])
    ds.createDimension('COL', grid['ncol'])
    
    # 全局属性（使用模板的特殊值）
    now = datetime.now()
    ds.IOAPI_VERSION = "ioapi-3.2: $Id: init3.F90 185 2020-08-28 16:49:45Z coats $"
    ds.EXEC_ID = "????????????????"
    ds.FTYPE = 1
    ds.CDATE = int(now.strftime("%Y%j"))
    ds.CTIME = int(now.strftime("%H%M%S"))
    ds.WDATE = ds.CDATE
    ds.WTIME = ds.CTIME
    ds.SDATE = 0
    ds.STIME = 0
    ds.TSTEP = 0
    ds.NTHIK = 1
    ds.NCOLS = grid['ncol']
    ds.NROWS = grid['nrow']
    ds.NLAYS = 1
    ds.NVARS = nvars
    ds.GDTYP = grid['gdtyp']
    ds.P_ALP = grid['p_alp']
    ds.P_BET = grid['p_bet']
    ds.P_GAM = grid['p_gam']
    ds.XCENT = grid['xcent']
    ds.YCENT = grid['ycent']
    ds.XORIG = grid['xorig']
    ds.YORIG = grid['yorig']
    ds.XCELL = grid['xcell']
    ds.YCELL = grid['ycell']
    # 关键：使用模板的特殊值
    ds.VGTYP = -9999
    ds.VGTOP = -9.e36
    ds.VGLVLS = np.array([-9999.0, -9999.0], dtype=np.float32)
    ds.GDNAM = f"{domain}_GRID".ljust(16)
    ds.UPNAM = "NORMBEIS370"
    
    # VAR-LIST
    var_list_str = ''.join([f"{v:<16}" for v in TEMPLATE_VARS])
    setattr(ds, 'VAR-LIST', var_list_str)
    
    ds.FILEDESC = "BEIS3 normalized emissions values."
    ds.HISTORY = ""
    
    # TFLAG 变量
    tflag = ds.createVariable('TFLAG', np.int32, ('TSTEP', 'VAR', 'DATE-TIME'))
    tflag.units = "<YYYYDDD,HHMMSS>"
    tflag.long_name = "TFLAG"
    tflag.var_desc = "Timestep-valid flags: (1) YYYYDDD or (2) HHMMSS"
    tflag[:] = 0
    
    # 创建所有变量并写入数据
    for var_name in TEMPLATE_VARS:
        var = ds.createVariable(var_name, np.float32, ('TSTEP', 'LAY', 'ROW', 'COL'))
        var.long_name = var_name.ljust(16)
        var.var_desc = "normalized emissions"
        
        if var_name.startswith('LAI_'):
            var.units = "index"
            # LAI 变量：夏季和冬季使用不同的数据
            if var_name.endswith('S'):
                var[0, 0, :, :] = summer.get(var_name, np.zeros((grid['nrow'], grid['ncol'])))
            else:
                var[0, 0, :, :] = winter.get(var_name, np.zeros((grid['nrow'], grid['ncol'])))
        elif var_name in ['AVG_NOAG_GROW', 'AVG_NOAG_NONGROW', 'AVG_NONONAG']:
            var.units = "g N/m²-hr"
            var[0, 0, :, :] = summer.get(var_name, np.zeros((grid['nrow'], grid['ncol'])))
        else:
            var.units = "g C/m²-hr"
            if var_name.endswith('S'):
                var[0, 0, :, :] = summer.get(var_name, np.zeros((grid['nrow'], grid['ncol'])))
            else:
                var[0, 0, :, :] = winter.get(var_name, np.zeros((grid['nrow'], grid['ncol'])))
    
    ds.close()
    print(f"✅ 生成成功: {out_path}")
    print(f"   变量数: {nvars}")
    print(f"   网格: {grid['nrow']}x{grid['ncol']}")


def process_domain(domain, summer_month, winter_month):
    print(f"\n{'=' * 60}")
    print(f"处理区域: {domain}")
    
    # 提取基础域名称（用于查找 WRF 生物文件）
    if '_' in domain and domain[:2] == 'd0':
        base_domain = domain.split('_')[0]
        print(f"  基础域: {base_domain} (用于查找 WRF 生物文件)")
    else:
        base_domain = domain
    
    try:
        grid_f, lufrac_f, met_f = find_mcip_files(domain)
        date_str = extract_date_from_filename(met_f)
        wrf_f = find_wrfbiochemi_file(base_domain)
    except Exception as e:
        print(f"❌ 文件查找失败: {e}")
        return False
    
    print(f"  GRIDCRO2D: {os.path.basename(grid_f)}")
    print(f"  LUFRAC_CRO: {os.path.basename(lufrac_f)}")
    print(f"  WRF BIO: {os.path.basename(wrf_f)}")
    print(f"  日期: {date_str}")
    
    # 网格信息
    try:
        grid = get_grid_info_from_mcip(grid_f)
    except Exception as e:
        print(f"❌ 网格信息读取失败: {e}")
        return False
    print(f"  CMAQ网格: {grid['nrow']}x{grid['ncol']}")
    
    # 土地利用 & 土壤NO
    try:
        lu = get_landuse_from_lufrac(lufrac_f)
        soil_no = get_soil_no_from_landuse(lu)
    except:
        print("⚠️ 使用默认土壤NO值")
        soil_no = np.ones((grid['nrow'], grid['ncol']), dtype=np.float32) * 10.0
    
    # 读取WRF数据
    try:
        wrf_ds = nc.Dataset(wrf_f, 'r')
        wrf_nr, wrf_nc = get_wrf_dimensions(wrf_ds)
        rs, re, cs, ce = calculate_crop_indices(wrf_nr, wrf_nc, grid['nrow'], grid['ncol'])
        isop, mono, ovoc = get_wrf_emission_factors(wrf_ds, rs, re, cs, ce)
        lai_s = get_lai_data(wrf_ds, summer_month, rs, re, cs, ce)
        lai_w = get_lai_data(wrf_ds, winter_month, rs, re, cs, ce)
        wrf_ds.close()
    except Exception as e:
        print(f"❌ WRF数据读取失败: {e}")
        return False
    
    # 计算排放
    grid_area_km2 = (grid['xcell'] * grid['ycell']) / 1_000_000.0
    
    summer_data = calculate_emissions(isop, mono, ovoc, soil_no, lai_s, grid_area_km2, season="summer")
    winter_data = calculate_emissions(isop, mono, ovoc, soil_no, lai_w, grid_area_km2, season="winter")
    
    # 输出
    os.makedirs(B3GRD_OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(B3GRD_OUTPUT_DIR, f"B3GRD_{domain}.nc")
    write_b3grd_file(out_path, grid, summer_data, winter_data, domain, date_str)
    return True


def main():
    if len(sys.argv) != 4:
       
        print("示例: python3 wrfbiochemi_to_b3grd.py d01 7 1")
        sys.exit(1)
    
    domain_arg = sys.argv[1]
    sm = int(sys.argv[2])
    wm = int(sys.argv[3])
    
    if not (1 <= sm <= 12 and 1 <= wm <= 12):
        print("❌ 月份必须 1~12")
        sys.exit(1)
    
  
    
    print("=" * 60)
    print("WRF-Chem → CMAQ BEIS3.61 B3GRD 转换工具")
    print("=" * 60)
    print(f"WRF BIO目录: {WRFBIOCHEMI_DIR}")
    print(f"MCIP目录: {MCIP_DIR}")
    print(f"输出目录: {B3GRD_OUTPUT_DIR}")
    print(f"处理域: {domain_arg}")
    
   # for d in domains:
    process_domain(domain_arg, sm, wm)
    
    print("\n" + "=" * 60)
    print("全部处理完成！")


if __name__ == '__main__':
    main()
