#!/bin/csh -f

# ==================================================================
#> Runtime Environment Options
# ==================================================================

#> 选择编译器选项
 setenv compiler intel 
#> 激活环境设置脚本
 source $CMAQ_HOME/config_cmaq.csh $compiler
#> 检查环境变量 CMAQ_DATA 是否设置
 if ( ! -e $CMAQ_DATA ) then
    echo "   $CMAQ_DATA path does not exist"
    exit 1
 endif
 echo " "; echo " Input data path, CMAQ_DATA set to $CMAQ_DATA"; echo " "

#> 设置模拟配置通用参数
 set VRSN     = v532                    #> Code Version
 set APPL     = 202409             #> Application Name
 set ICTYPE   = regrid                  #> Initial conditions type [profile|regrid] 这里有两种模式，我倾向于regrid

#> 设置icon的可执行程序工作目录
 set BLD      = ${CMAQ_HOME}/PREP/icon/scripts/BLD_ICON_${VRSN}_${compiler}
 set EXEC     = ICON_${VRSN}.exe  
 cat $BLD/ICON_${VRSN}.cfg; echo " "; set echo

#> 水平网格定义
 setenv GRID_NAME d03_202409              #> 查看 GRIDDESC 文件的GRID_NAME 选项，其实就是嵌套域名称
 setenv GRIDDESC $CMAQ_DATA/mcip/$GRID_NAME/GRIDDESC  #> MCIP输出的网格描述文件 
 setenv IOAPI_ISPH 20                     #> GCTP 球体参数，WRF模式用20

#> I/O 控制（不用动）
 setenv IOAPI_LOG_WRITE F     #> 开启WRITE3日志目录 [ options: T | F ]
 setenv IOAPI_OFFSET_64 YES   #> 支持大时间步记录 [ options: YES | NO ],其实就是IOAPI的NETCDF3_64BIT_OFFSET格式
 setenv EXECUTION_ID $EXEC    #> 定义可执行文件的ID

# =====================================================================
#> ICON 配置选项
#
# ICON 有两种运行模式                                   
#     1) 重新网格化，从 CMAQ CCTM的输出开始 (IC type = regrid)     
#     2) 默认理想清洁剖面，垂直轮廓线开始 (IC type = profile)
# =====================================================================

 setenv ICON_TYPE ` echo $ICTYPE | tr "[A-Z]" "[a-z]" ` 

# =====================================================================
#> 输入/输出目录
# =====================================================================

 set OUTDIR   = $CMAQ_DATA/icon/$GRID_NAME      #> 输出文件目录

# =====================================================================
#> 输入文件
#  
# 重网格模式 (IC = regrid) (包括嵌套域、窗口域或常规重网格域)
#     CTM_CONC_1 = 粗网格CCTM的浓度文件(d02的CCTM输出，CONC文件，不是ACONC文件)          
#     MET_CRO_3D_CRS = 粗网格 MET_CRO_3D 气象文件(d02的MCIP输出)  
#     MET_CRO_3D_FIN = 目标嵌套域网格的 MET_CRO_3D 气象文件
#                                                                            
#  剖面模式 (IC = profile)
#     IC_PROFILE = 静态/默认 IC profiles 文件（就那几个csv文件）
#     MET_CRO_3D_FIN = 目标嵌套域网格的 MET_CRO_3D 气象文件
#
# 注意: SDATE (yyyyddd) 和 STIME (hhmmss) 的设置只与regrid模式相关
#        如果未设置将从 MET_CRO_3D_FIN 文件中获取
# =====================================================================
#> 输出文件
#     INIT_CONC_1 = 目标嵌套域的网格化 IC文件
# =====================================================================

    set DATE = "2024-09-05"
    set YYYYJJJ  = `date -ud "${DATE}" +%Y%j`   #> Convert YYYY-MM-DD to YYYYJJJ
    set YYMMDD   = `date -ud "${DATE}" +%y%m%d` #> Convert YYYY-MM-DD to YYMMDD
    set YYYYMMDD = `date -ud "${DATE}" +%Y%m%d` #> Convert YYYY-MM-DD to YYYYMMDD
    set YYYYMM = `date -ud "${DATE}" +%Y%m`       #> Convert YYYY-MM-DD to YYYYMM 四个字符的年份再加上月份，没日期
#   setenv SDATE           ${YYYYJJJ}
#   setenv STIME           000000

 if ( $ICON_TYPE == regrid ) then
    setenv CTM_CONC_1 $CMAQ_DATA/cctm/output_CCTM_v532_intel_d02_202409/CCTM_CONC_v532_intel_d02_202409_${YYYYMMDD}.nc
    setenv MET_CRO_3D_CRS $CMAQ_DATA/mcip/d02_202409/METCRO3D_${YYYYMM}.nc
    setenv MET_CRO_3D_FIN $CMAQ_DATA/mcip/$GRID_NAME/METCRO3D_${YYYYMM}.nc
    setenv INIT_CONC_1    "$OUTDIR/ICON_${VRSN}_${GRID_NAME}_${ICON_TYPE}_${YYYYMM} -v"
 endif

 if ( $ICON_TYPE == profile ) then
    setenv IC_PROFILE $BLD/avprofile_cb6r3m_ae7_kmtbr_hemi2016_v53beta2_m3dry_col051_row068.csv
    setenv MET_CRO_3D_FIN $CMAQ_DATA/mcip/$GRID_NAME/METCRO3D_${YYYYMM}.nc
    setenv INIT_CONC_1    "$OUTDIR/ICON_${VRSN}_${GRID_NAME}_${ICON_TYPE}_${YYYYMM} -v"
 endif
 
#>- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
#创建输出目录
 if ( ! -d "$OUTDIR" ) mkdir -p $OUTDIR

#显示可执行文件信息
 ls -l $BLD/$EXEC; size $BLD/$EXEC
 unlimit
 limit

#> 执行可执行文件:
 time $BLD/$EXEC

 exit() 
