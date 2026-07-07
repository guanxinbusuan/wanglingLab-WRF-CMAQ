#!/bin/csh -f

# ===================== CCTMv5.3.X Run Script ========================= 
# Usage: run.cctm >&! cctm_2016_12US1.log &                                
#
# To report problems or request help with this script/program:
#             http://www.epa.gov/cmaq    (EPA CMAQ Website)
#             http://www.cmascenter.org  (CMAS Website)
# ===================================================================  

# ===================================================================
#> 运行时环境选项
# ===================================================================

echo 'Start Model Run At ' `date`

#> 切换诊断模式，该模式会将详细信息输出到标准输出 
 setenv CTM_DIAG_LVL 0   #> 0为关闭诊断输出	

#> 编译器和版本选项 Options: intel | gcc | pgi
 if ( ! $?compiler ) then
   setenv compiler intel
 endif
 if ( ! $?compilerVrsn ) then
   setenv compilerVrsn Empty
 endif

#> 激活cmaq设置脚本
 source $CMAQ_HOME/config_cmaq.csh $compiler $compilerVrsn
 cd $CMAQ_HOME/CCTM/scripts

#> 模拟通用设置
 set VRSN      = v532              #>  源码版本
 set PROC      = mpi               #> 并行或串行设置
 set MECH      = cb6r3_ae7_aq      #> 化学机制
 set EMIS      = emiss_meic_d02_202409            #> 排放清单名称
 set APPL      = d03_202409        #> Application Name (e.g. Gridname)

#> 将 RUNID 定义为上述参数或其他参数的任意组合。默认情况下，
#> 这些信息会被汇总到 $RUNID 这一个字符串中，以方便在输出二进制文件、
#> 日志文件及其他脚本中进行引用。
 setenv RUNID  ${VRSN}_${compiler}_${APPL}

#> 设置构建目录（CMAQ 可执行文件默认存放于此）。
 set BLD       = ${CMAQ_HOME}/CCTM/scripts/BLD_CCTM_${VRSN}_${compiler}
 set EXEC      = CCTM_${VRSN}.exe  

#> 将运行脚本的每一行输出到日志文件
 if ( $CTM_DIAG_LVL != 0 ) set echo 

#> 设置工作目录、输入目录和输出目录
 setenv WORKDIR ${CMAQ_HOME}/CCTM/scripts       #> 工作目录。即运行脚本所在的位置。
 setenv OUTDIR  ${CMAQ_DATA}/cctm/output_CCTM_${RUNID}    #> 输出目录
 setenv INPDIR  ${CMAQ_DATA}                           #> 输入文件目录
 setenv LOGDIR  ${OUTDIR}/LOGS     #> 日志文件目录
 setenv NMLpath ${BLD}             #> Location of Namelists. Common places are: 
                                   #>   ${WORKDIR} | ${CCTM_SRC}/MECHS/${MECH} | ${BLD}

 echo ""
 echo "Working Directory is $WORKDIR"
 echo "Build Directory is $BLD"
 echo "Output Directory is $OUTDIR"
 echo "Log Directory is $LOGDIR"
 echo "Executable Name is $EXEC"

# =====================================================================
#> CCTM 配置选项
# =====================================================================
#> 设置循环的起始和结束日期（包含当天完整的0-23h）
 setenv NEW_START TRUE             #> 设为 FALSE 以进行模型重启（从已有状态继续运行）
 set START_DATE = "2024-09-05"     #> 开始日期
 set END_DATE   = "2024-09-08"     #> 结束日期

#> 设置时间步进参数(这里绝对不能动!!!)
set STTIME     = 000000            #> 起始 GMT 时间（HHMMSS，时分秒格式）  模拟开始的小时时刻   其实按照这一套流程，这里只能是0小时
set NSTEPS     = 240000            #> 在逐日循环中，每一天的 NSTEPS 应该只跑 24 小时。 其实按照这一套循环模拟流程，这里也不能动     
set TSTEP      = 010000            #> 输出时间步长间隔（HHMMSS，时分秒格式） 隔多久写出一帧 ,这里也不能动

	#> 水平域分解
if ( $PROC == serial ) then
   setenv NPCOL_NPROW "1 1"; set NPROCS   = 1  # 单核设置 / 串行模式设置
else
   @ NPCOL  =  14; @ NPROW =  13
   @ NPROCS = $NPCOL * $NPROW
   setenv NPCOL_NPROW "$NPCOL $NPROW"; 
endif

#> 定义运行ID： e.g. [CMAQ-Version-Info]_[User]_[Date]_[Time]
setenv EXECUTION_ID "CMAQ_CCTM${VRSN}_`id -u -n`_`date -u +%Y%m%d_%H%M%S_%N`"    #> 向 IO/API 告知执行 ID
echo ""
echo "---CMAQ EXECUTION ID: $EXECUTION_ID ---"

#> 保留或删除已有输出文件
set CLOBBER_DATA = TRUE  #设置为TRUE则为覆盖模式，如果使用了daymixtocmaq.py生成的清单文件则必须为TRUE，因为有儒略日循环

#> 日志文件选项
#> 主日志文件名；取消注释可将标准输出写入日志，否则输出到屏幕
setenv LOGFILE $LOGDIR/$RUNID.log
if (! -e $LOGDIR ) then
  mkdir -p $LOGDIR
endif
setenv PRINT_PROC_TIME Y                #> 将所有科学子进程的计时信息输出到日志文件[ default: TRUE or Y ]
setenv STDOUT T                         #> 覆盖 I/O-API 尝试同时向处理器日志和 STDOUT 写入信息的行为[ options: T | F ]
setenv GRID_NAME d03_202409             #> 查看 GRIDDESC 文件中的 GRID_NAME 选项
setenv GRIDDESC $INPDIR/mcip/$GRID_NAME/GRIDDESC        #>MCIP输出的网格描述文件

#> 获取本次模拟中的列数、行数和层数
set NZ = 34                            #>BCON输出文件里面有这个高度层数，直接相等即可
set NX = `grep -A 1 ${GRID_NAME} ${GRIDDESC} | tail -1 | sed 's/  */ /g' | cut -d' ' -f6`  
set NY = `grep -A 1 ${GRID_NAME} ${GRIDDESC} | tail -1 | sed 's/  */ /g' | cut -d' ' -f7`
set NCELLS = `echo "${NX} * ${NY} * ${NZ}" | bc -l`

#> 输出物种和层选项
   #> CONC 文件物种；注释掉或设为 "ALL" 可将所有物种写入 CONC  （瞬时浓度）
   #setenv CONC_SPCS "O3 NO ANO3I ANO3J NO2 FORM ISOP NH3 ANH4I ANH4J ASO4I ASO4J" 
   #setenv CONC_BLEV_ELEV " 1 1"        #> CONC 文件层范围；注释掉可将所有高度层写入 CONC  当前是只写入第一层浓度

  #> ACONC 文件物种；注释掉或设为 "ALL" 可将所有物种写入 ACONC  （平均浓度）
   #setenv AVG_CONC_SPCS "O3 NO CO NO2 ASO4I ASO4J NH3"
   setenv AVG_CONC_SPCS "ALL" 
   setenv ACONC_BLEV_ELEV " 1 1"  #> ACONC 文件层范围；注释掉可将所有高度层写入 ACONC   当前是只写入第一层浓度
   setenv AVG_FILE_ENDTIME N     #> 覆盖 ACONC 文件默认的起始时间戳 [ default: N ] 使用模型自动确定的默认起始时间戳 建议保持为 N

#> 同步时间步长与容差选项
setenv CTM_MAXSYNC 300       #> 最大同步时间步长（秒）[ 默认值：720 ]
setenv CTM_MINSYNC  60       #> 最小同步时间步长（秒）[ 默认值：60 ]
setenv SIGMA_SYNC_TOP 0.7    #> 用于确定同步时间步的最高 sigma 层 [ 默认值：0.7 ]  模型只考虑从地表到 sigma = 0.7（约 700 hPa 附近，对流层中下部）这一层范围内的气象条件来计算同步步长
setenv ADV_HDIV_LIM 0.95    #> 平流时间步调整的最大水平散度限制 [ default: 0.9 ]
setenv CTM_ADV_CFL 0.75      #> 最大 CFL 数 [ default: 0.75]
setenv RB_ATOL 1.0E-07      #> 全局 ROS3 求解器绝对容差 [ default: 1.0E-07 ] 

#> 科学计算选项 大部分选项都是 Y/N
setenv CTM_OCEAN_CHEM N      #> 海洋卤素化学和海盐气溶胶排放的开关 [ default: Y ]
setenv CTM_WB_DUST N         #> 使用在线风蚀粉尘排放 [ default: Y ]
setenv CTM_WBDUST_BELD BELD3 #> 用于识别沙尘源区的土地利用数据库 [ 默认值：BELD3 ]；若 CTM_WB_DUST = N 则忽略                       
setenv CTM_LTNG_NO N         #> 开启闪电 NOx [ 默认值：N ]
setenv KZMIN Y               #> 在 edyintb (CMAQ 垂直扩散（EDDY）模块中的子程序)中使用Min Kz参数化方案 [ default: Y ], 设为 N 则回退到 Kz0UT 方案
setenv CTM_MOSAIC Y          #> 按土地利用类型区分的沉降速度 [ 默认值：N ]
setenv CTM_FST Y             #> 获取土地利用特异性气孔通量的 mosaic 方法   [ default: N ]  
setenv PX_VERSION N          #> WRF PX 陆面模式
setenv CLM_VERSION N         #> WRF CLM 陆面模式
setenv NOAH_VERSION Y        #> WRF NOAH 陆面模式 ，这三个CCTM的陆气反馈的设置要和WRF中 namelsit.input文件设置的陆面模式兼容
setenv CTM_ABFLUX N           #> 氨（NH3）在线沉降速度的双向通量 [ 默认值：N ]
setenv CTM_BIDI_FERT_NH3 F    #> 从排放中扣除施肥产生的 NH3，因为其将由双向通量（BiDi）计算处理 [ 选项：T/F ]
setenv CTM_HGBIDI N           #> 汞（Hg）在线沉降速度的双向通量 [ 默认值：N ]
setenv CTM_SFC_HONO Y        #> 地表 HONO 相互作用  [ default: Y ]
setenv CTM_GRAV_SETL Y       #> 垂直扩散中的气溶胶重力沉降 [ default: Y ]
setenv CTM_BIOGEMIS Y        #> 计算在线生物源排放 [ default: N ]

#>  垂直提取选项，只有当需要和地面站点做时序浓度的资料同化时才启用，否则不用管
setenv VERTEXT N
setenv VERTEXT_COORD_PATH ${WORKDIR}/lonlat.csv

#> I/O 控制设置
setenv IOAPI_LOG_WRITE F     #> 启用额外的 WRITE3 日志记录  [ options: T | F ]
setenv FL_ERR_STOP N         #> 遇到不一致的输入文件时停止运行 [ options: Y | N ]
setenv PROMPTFLAG F          #> 开启 I/O-API PROMPT*FILE 交互模式 [ options: T | F ] 集群/队列系统（SLURM/PBS）提交时必须关闭
setenv IOAPI_OFFSET_64 YES   #> 支持大时间步记录（单条记录 > 2GB）[ 选项：YES | NO ] 其实就是 NETCDF3的 64-bit offset 格式 （这个必须 YES）
setenv IOAPI_CHECK_HEADERS N #> 检查文件头信息 [ options: Y | N ]
setenv CTM_EMISCHK N         #> 若排放输入文件中缺失替代物种（surrogates），则终止 CMAQ 运行 [ options: Y | N ]

setenv EMISDIAG F            #> 在输出时间步打印经用户规则缩放和修改后的排放速率 [ 选项：F | T 或 2D | 3D | 2DSUM ] 
                             #>  各独立排放源可分别通过以下变量控制：
                             #>       GR_EMIS_DIAG_## | STK_EMIS_DIAG_## | BIOG_EMIS_DIAG
                             #>       MG_EMIS_DIAG    | LTNG_EMIS_DIAG   | DUST_EMIS_DIAG
                             #>       SEASPRAY_EMIS_DIAG   
                             #>   注意：这些诊断输出与其他排放诊断不同，因为它们发生在缩放操作之后。

setenv EMISDIAG_SUM F        #>  将排放速率总和输出到网格化诊断文件


#>  诊断输出标志
setenv CTM_CKSUM Y           #> 校验和报告 [ default: Y ]
setenv CLD_DIAG N            #> 云(气象概念的云)诊断文件 [ default: N ]
setenv CTM_PHOTDIAG N        #> 光解诊断文件 [ default: N ]
setenv NLAYS_PHOTDIAG "1"    #> PHOTDIAG2和PHOTDIAG3（光学/光解诊断输出文件）的输出层数。从第 1 层输出至 NLAYS_PHOTDIAG 层 [ default: all layers ] 当前为第一层输出
setenv NWAVE_PHOTDIAG "294 303 310 316 333 381 607"  #>  输出到 PHOTDIAG2 和 PHOTDIAG3 文件的辐射波长波段（nm） [ default: all wavelengths ]  [ 默认：所有波长波段 ]
setenv CTM_PMDIAG N          #> 瞬时气溶胶诊断文件[ default: Y ]
setenv CTM_APMDIAG Y         #> 小时平均气溶胶诊断文件[ default: Y ]
setenv APMDIAG_BLEV_ELEV "1 1"  #> 平均 PMDIAG （颗粒物诊断文件）的层范围 = NLAYS （目前设置 1 到 1 层）
setenv CTM_SSEMDIAG N        #> 海盐排放诊断文件 [ default: N ]
setenv CTM_DUSTEM_DIAG N     #> 风蚀沙尘排放诊断文件[ default: N ]; 若 CTM_WB_DUST = N 则忽略
setenv CTM_DEPV_FILE N       #> 沉降速度诊断文件 [ default: N ]
setenv VDIFF_DIAG_FILE N     #> 垂直扩散及气溶胶重力沉降诊断文件 [ default: N ]
setenv LTNGDIAG N            #> 闪电诊断文件 [ default: N ]
setenv B3GTS_DIAG Y          #>  BEIS （生物源排放清单系统）质量排放诊断文件 [ default: N ]
setenv CTM_WVEL Y            #>  将导出的垂直速度分量保存到浓度文件 [ default: Y ]

# =====================================================================
#> 输入目录和文件名
# =====================================================================

set ICpath    = $INPDIR/icon/$GRID_NAME              #> 初始条件（ ICON 输出）输入目录
set BCpath    = $INPDIR/bcon/$GRID_NAME              #> 边界条件( BCON 输出 )输入目录
set EMISpath  = $INPDIR/MIX_to_cmaq/$GRID_NAME        #>  面源排放输入目录        脚本MIXtocmaq的输出文件路径
set EMISpath2 = $INPDIR/MIX_to_cmaq/$GRID_NAME	            #> 地表居民燃木燃烧排放目录      当前不用管
set IN_PTpath = $INPDIR/emis/cb6r3_ae6_20190221/cmaq_ready                 #> 高架排放输入目录（仅在线点源）    当前不用管
set IN_LTpath = $INPDIR/met/lightning     #>  闪电 NOx 输入目录 
set METpath   = $INPDIR/mcip/$GRID_NAME   #>  气象输入目录
#set JVALpath  = $INPDIR/jproc            #>  离线光解速率表目录
set OMIpath   = $BLD                      #>  用于光解模型的臭氧柱数据
set LUpath    = $INPDIR/surface           #> 风蚀沙尘模型的 BELD 土地利用数据
set SZpath    = $INPDIR/surface           #> 在线海盐气溶胶排放的碎浪带文件 

# =====================================================================
#> 开始 CCTM 的逐日模拟循环
# =====================================================================
set rtarray = ""

set TODAYG = ${START_DATE}
set TODAYJ = `date -ud "${START_DATE}" +%Y%j` #> Convert YYYY-MM-DD to YYYYJJJ 注释：J 是 Julian Day（儒略日/年积日），即一年中的第几天。
set START_DAY = ${TODAYJ} 
set STOP_DAY = `date -ud "${END_DATE}" +%Y%j` #> Convert YYYY-MM-DD to YYYYJJJ
set NDAYS = 0
set START_YYYYMM = `date -ud "${START_DATE}" +%Y%m`    #> 排放文件0-25h循环（就是daymixtocmaq.py 生成的） 使用这个变量 四个字符的年份再加上月份，没日期，对应之前的步骤的 APPL 变量

while ($TODAYJ <= $STOP_DAY )               #>Compare dates in terms of YYYYJJJ 按 YYYYJJJ 格式比较日期
  
  set NDAYS = `echo "${NDAYS} + 1" | bc -l`

  #> 获取 CCTM 模拟的日历日期信息
  set YYYYMMDD = `date -ud "${TODAYG}" +%Y%m%d` #> Convert YYYY-MM-DD to YYYYMMDD  
  set YYYYMM = `date -ud "${TODAYG}" +%Y%m`     #> Convert YYYY-MM-DD to YYYYMM
  set YYYY = `date -ud "${TODAYG}" +%Y`         #> Convert YYYY-MM-DD to YYYY
  set YYMMDD = `date -ud "${TODAYG}" +%y%m%d`   #> Convert YYYY-MM-DD to YYMMDD
  set YYYYJJJ = $TODAYJ

  #> 计算昨天的日期 
  set YESTERDAY = `date -ud "${TODAYG}-1days" +%Y%m%d` #> Convert YYYY-MM-DD to YYYYJJJ 

# =====================================================================
#> 设置输出字符串并传播模型配置文档
# =====================================================================
  echo ""
  echo "Set up input and output files for Day ${TODAYG}."

  #>  设置输出文件扩展名
  setenv CTM_APPL ${RUNID}_${YYYYMMDD} 
  
  #>  将模型配置复制到输出文件夹
  if ( ! -d "$OUTDIR" ) mkdir -p $OUTDIR
  cp $BLD/CCTM_${VRSN}.cfg $OUTDIR/CCTM_${CTM_APPL}.cfg

# =====================================================================
#>  输入文件（部分随日期变化）
# =====================================================================

  #> 初始条件 其实就是 ICON输出的 IC 场文件
  if ($NEW_START == true || $NEW_START == TRUE ) then
     set ICpath = ${CMAQ_DATA}/icon/${GRID_NAME}
     setenv ICFILE ICON_v532_d03_202409_regrid_202409
     #> setenv INIT_MEDC_1 notused            #> MEDC 通常与嵌套网格或多尺度初始条件相关；notused 表示本次模拟不需要该功能
     # > 与土壤信息重启文件相关 
     setenv INITIAL_RUN N                  #>设置为 Y ,则土壤变量由默认值或外部输入初始化，不读取 SOILINP 文件。相当于"土壤从零开始"。
  else
     set ICpath = $OUTDIR
     setenv ICFILE CCTM_CGRID_${RUNID}_${YESTERDAY}.nc
     setenv INIT_MEDC_1 $ICpath/CCTM_MEDIA_CONC_${RUNID}_${YESTERDAY}.nc
     setenv INITIAL_RUN N
  endif

  #>边界条件；若 CCTM 对干沉降速度（depv）使用 STAGE 方案选项（当前是默认的 M3DRY 方案选项）， 则需使用 STAGE 版本的边界条件文件
  #set BCFILE = bctr_12km_HCMAQ_V53BETA2_STAGE_cb6r3m_ae7_kmtbr_BCON_V53_${YYYYMM}.ncf
  #set BCFILE = bctr_12km_HCMAQ_V53R_RUNA_M3DRY_cb6r3m_ae7_kmtbr_BCON_V53_${YYYYMM}.ncf
  set BCFILE = BCON_v532_d03_202409_regrid_202409       #> 边界条件 其实就是 BCON输出的 BC 场文件
  
  #>  离线光解速率表文件
  #set JVALfile  = JTABLE_${YYYYJJJ}

  #> 臭氧柱数据
  set OMIfile   = OMI_1979_to_2019.dat

  #> 光学特性文件
  set OPTfile = PHOT_OPTICS.dat

  #>  MCIP输出的气象文件
  setenv GRID_BDY_2D $METpath/GRIDBDY2D_${START_YYYYMM}.nc
  setenv GRID_CRO_2D $METpath/GRIDCRO2D_${START_YYYYMM}.nc
  setenv GRID_CRO_3D $METpath/GRIDCRO3D_${START_YYYYMM}.nc
  setenv GRID_DOT_2D $METpath/GRIDDOT2D_${START_YYYYMM}.nc
  setenv MET_CRO_2D  $METpath/METCRO2D_${START_YYYYMM}.nc
  setenv MET_CRO_3D  $METpath/METCRO3D_${START_YYYYMM}.nc
  setenv MET_DOT_3D  $METpath/METDOT3D_${START_YYYYMM}.nc
  setenv MET_BDY_3D  $METpath/METBDY3D_${START_YYYYMM}.nc
  setenv LUFRAC_CRO  $METpath/LUFRAC_CRO_${START_YYYYMM}.nc

  #> 排放控制文件
  #> 重要提示
  #> 下面定义的排放控制文件是控制模型模拟行为的核心组成部分。
  #> 除其他功能外，它控制排放文件中的物种到模型化学物种的映射， 以及有机气溶胶模拟的多个相关方面。
  #> 请仔细审查排放控制文件，确保其配置与创建下面定义的排放文件时所采用的假设、以及有机气溶胶的期望表征方式保持一致。
  #> 更多信息请参阅：
  #>   + AERO7 发布说明中的"必需的排放更新"部分：
  #>   https://github.com/USEPA/CMAQ/blob/master/DOCS/Release_Notes/aero7_overview.md
  #>  + CMAQ 用户指南第 6.9.3 节"排放兼容性"：
  #>   https://github.com/USEPA/CMAQ/blob/master/DOCS/Users_Guide/CMAQ_UG_ch06_model_configuration_options.md#6.9.3_Emission_Compatability
  #>   + CMAQ 用户指南中的排放控制（DESID）文档：
  #>   https://github.com/USEPA/CMAQ/blob/master/DOCS/Users_Guide/Appendix/CMAQ_UG_appendixB_emissions_control.md 
  #>
  setenv EMISSCTRL_NML ${BLD}/EmissCtrl_${MECH}.nml    #>这个不能动 这个关系到排放清单的物种变量名称的映射

  #> 用于排放缩放的空间掩膜
  setenv CMAQ_MASKS $SZpath/12US1_surf.ncf

  #> 忽略你生成的排放清单文件的日期检查，配合 daymixtocmaq.py 使用
  setenv EMIS_SYM_DATE T    

  #> 确定代表性排放日
  #set EMDATES = $INPDIR/emis/emis_dates/smk_merge_dates_${YYYYMM}.txt
  #set intable = `grep "^${YYYYMMDD}" $EMDATES`
  #set Date     = `echo $intable[1] | cut -d, -f1`
  #set aveday_N = `echo $intable[2] | cut -d, -f1`
  #set aveday_Y = `echo $intable[3] | cut -d, -f1`
  #set mwdss_N  = `echo $intable[4] | cut -d, -f1`
  #set mwdss_Y  = `echo $intable[5] | cut -d, -f1`
  #set week_N   = `echo $intable[6] | cut -d, -f1`
  #set week_Y   = `echo $intable[7] | cut -d, -f1`
  #set all      = `echo $intable[8] | cut -d, -f1`

  #> 网格化（面源）排放文件设置                  daymixtocmaq.py 其实把整个 MIX 清单都当面源处理了
  setenv N_EMIS_GR 1                      
  #>setenv N_EMIS_GR 2                         #> 面源排放文件数量  说白了很智能，能搞一大堆排放清单丢进来
  set EMISfile  = emis_meic_cb6r3_ae7_aq_20240905_d03_daily.nc
  setenv GR_EMIS_001 ${EMISpath}/${EMISfile}
  setenv GR_EMIS_LAB_001 GRIDDED_EMIS01
  #setenv GR_EM_SYM_DATE_001 F                # 如需更改默认行为，请参阅 EMIS_SYM_DATE 用户指南。
  setenv GR_EM_SYM_DATE_001 T                #> 忽略日期检查 配合 daymixtocmaq.py 使用
  setenv GR_EMISLAY 34                       #> 排放文件的高度层

  #set EMISfile  = emis_mole_rwc_${YYYYMMDD}_12US1_cmaq_cb6_2016ff_16j.ncf
  #setenv GR_EMIS_002 ${EMISpath2}/${EMISfile}
  #setenv GR_EMIS_LAB_002 GRIDDED_RWC
  #setenv GR_EM_SYM_DATE_002 F                # 如需更改默认行为，请参阅 EMIS_SYM_DATE 用户指南。
  
  #> 在线点源排放文件设置
  #setenv N_EMIS_PT 8                              #>高架源（点源）的排放文件数量
  #set STKCASEE = 12US1_cmaq_cb6_2016ff_16j        # > 在线排放速率文件后缀
  #set STKCASEG = 12US1_2016ff_16j                 # > 烟囱参数文件后缀

  #setenv STK_GRPS_001 $IN_PTpath/ptnonipm/stack_groups_ptnonipm_${STKCASEG}.ncf
  #setenv STK_GRPS_002 $IN_PTpath/ptegu/stack_groups_ptegu_${STKCASEG}.ncf
  #setenv STK_GRPS_003 $IN_PTpath/othpt/stack_groups_othpt_${STKCASEG}.ncf
  #setenv STK_GRPS_004 $IN_PTpath/ptagfire/stack_groups_ptagfire_${YYYYMMDD}_${STKCASEG}.ncf
  #setenv STK_GRPS_005 $IN_PTpath/ptfire/stack_groups_ptfire_${YYYYMMDD}_${STKCASEG}.ncf
  #setenv STK_GRPS_006 $IN_PTpath/ptfire_othna/stack_groups_ptfire_othna_${YYYYMMDD}_${STKCASEG}.ncf
  #setenv STK_GRPS_007 $IN_PTpath/pt_oilgas/stack_groups_pt_oilgas_${STKCASEG}.ncf
  #setenv STK_GRPS_008 $IN_PTpath/cmv_c3/stack_groups_cmv_c3_${STKCASEG}.ncf

  #setenv STK_EMIS_001 $IN_PTpath/ptnonipm/inln_mole_ptnonipm_${mwdss_Y}_${STKCASEE}.ncf
  #setenv STK_EMIS_002 $IN_PTpath/ptegu/inln_mole_ptegu_${YYYYMMDD}_${STKCASEE}.ncf
  #setenv STK_EMIS_003 $IN_PTpath/othpt/inln_mole_othpt_${mwdss_N}_${STKCASEE}.ncf
  #setenv STK_EMIS_004 $IN_PTpath/ptagfire/inln_mole_ptagfire_${YYYYMMDD}_${STKCASEE}.ncf
  #setenv STK_EMIS_005 $IN_PTpath/ptfire/inln_mole_ptfire_${YYYYMMDD}_${STKCASEE}.ncf
  #setenv STK_EMIS_006 $IN_PTpath/ptfire_othna/inln_mole_ptfire_othna_${YYYYMMDD}_${STKCASEE}.ncf
  #setenv STK_EMIS_007 $IN_PTpath/pt_oilgas/inln_mole_pt_oilgas_${mwdss_Y}_${STKCASEE}.ncf
  #setenv STK_EMIS_008 $IN_PTpath/cmv_c3/inln_mole_cmv_c3_${aveday_N}_${STKCASEE}.ncf

  #  为每个排放流标注标签
  #setenv STK_EMIS_LAB_001 PT_NONEGU
  #setenv STK_EMIS_LAB_002 PT_EGU
  #setenv STK_EMIS_LAB_003 PT_OTHER
  #setenv STK_EMIS_LAB_004 PT_AGFIRES
  #setenv STK_EMIS_LAB_005 PT_FIRES
  #setenv STK_EMIS_LAB_006 PT_OTHFIRES
  #setenv STK_EMIS_LAB_007 PT_OILGAS
  #setenv STK_EMIS_LAB_008 PT_CMV

  #setenv STK_EMIS_DIAG_001 2DSUM
  #setenv STK_EMIS_DIAG_002 2DSUM
  #setenv STK_EMIS_DIAG_003 2DSUM
  #setenv STK_EMIS_DIAG_004 2DSUM
  #setenv STK_EMIS_DIAG_005 2DSUM

  # 允许CMAQ使用点源文件，即使其日期与模型内部日期不一致  
  #setenv STK_EM_SYM_DATE_001 T   #> 如需更改默认行为，请参阅 EMIS_SYM_DATE 用户指南。
  #setenv STK_EM_SYM_DATE_002 T
  #setenv STK_EM_SYM_DATE_003 T
  #setenv STK_EM_SYM_DATE_004 T
  #setenv STK_EM_SYM_DATE_005 T
  #setenv STK_EM_SYM_DATE_006 T
  #setenv STK_EM_SYM_DATE_007 T
  #setenv STK_EM_SYM_DATE_008 T

  #>  闪电NOx配置
  if ( $CTM_LTNG_NO == 'Y' ) then
     setenv LTNGNO "InLine"    #>  将 LTNGNO 设为 "InLine" 以激活在线计算

  #> 在线闪电NOx选项
     setenv USE_NLDN  Y        #> 使用逐小时的 NLDN 闪电定位文件 [ default: Y ]
     if ( $USE_NLDN == Y ) then
        setenv NLDN_STRIKES ${IN_LTpath}/NLDN.12US1.${YYYYMMDD}.ioapi
     endif
     setenv LTNGPARMS_FILE ${IN_LTpath}/LTNG_AllParms_12US1.ncf # > 闪电参数文件；若 LTNGPARAM = N 则忽略
  endif

  #> 在线生物源排放配置
  if ( $CTM_BIOGEMIS == 'Y' ) then   
     set IN_BEISpath = $INPDIR/wrfbiochemi_to_cmaq/$GRID_NAME
     setenv GSPRO      ${BLD}/gspro_biogenics.txt
     setenv B3GRD      $IN_BEISpath/B3GRD_d03.nc
     setenv BIOSW_YN   N     #> 是否使用霜冻日期开关 [ default: Y ]
     setenv BIOSEASON  $IN_BEISpath/bioseason.cmaq.2016j_12US1.ncf_full #> 若 BIOSW_YN = N，则忽略季节开关文件
     setenv SUMMER_YN  Y     #>  是否使用夏季归一化排放 ? [ default: Y ]
     setenv PX_VERSION N     #> MCIP 是否为 WRF_PX 的陆面方案 ? [ default: N ]
     #> setenv NOAH_VERSION Y   
     setenv USE_WRF_LAI Y
     setenv LAI_VAR LAI
     setenv BIOG_SPRO B10C6AE7
     setenv SOILINP    $OUTDIR/CCTM_SOILOUT_${RUNID}_${YESTERDAY}.nc   #> 生物源 NO 土壤输入文件；若 INITIAL_RUN = Y 则忽略
  endif

  #> 风蚀粉尘排放配置
  if ( $CTM_WB_DUST == 'Y' ) then
     # BELD3 土地利用选项的输入变量
     setenv DUST_LU_1 $LUpath/beld3_12US1_459X299_output_a.ncf
     setenv DUST_LU_2 $LUpath/beld4_12US1_459X299_output_tot.ncf
  endif
  
  #> 在线海盐排放配置
  setenv OCEAN_1 $SZpath/12US1_surf.ncf        #> 海表温度（SST）、海冰覆盖分数、水深/海岸线掩膜 需要这个ncdf文件才能开启在线的海洋排放计算
 
  #> 双向氨配置  氨（NH₃）在大气和地表（土壤、植被）之间可以"双向"交换----既能从空气落到地面，也能从地面挥发到空气。
  if ( $CTM_ABFLUX == 'Y' ) then
     # 若使用 FEST-C v1.4 提供土壤数据，当前脚本里的耦合配置需要手动更新。 （说白了这里和 FEST-C的数据有兼容性问题）
     setenv E2C_SOIL ${INPDIR}/surface/toCMAQ_festc1.4_epic/us1_2016_cmaq12km_soil.nc
     setenv E2C_CHEM ${INPDIR}/surface/toCMAQ_festc1.4_epic/us1_2016_cmaq12km_time${YYYYMMDD}.nc
     setenv E2C_LU ${INPDIR}/surface/beld4_camq12km_2011_4CMAQioapi.ncf
  endif

#>  在线过程分析 PA 设置    追踪并量化每个化学/物理过程（平流、扩散、排放、沉降、气相化学、气溶胶过程等）对每个物种浓度的贡献  这里推荐关闭，用离线PA分析
  setenv CTM_PROCAN N        #> 是否使用过程分析 [ default: N]
  if ( $?CTM_PROCAN ) then   #>   若 $CTM_PROCAN 已定义
     if ( $CTM_PROCAN == 'Y' || $CTM_PROCAN == 'T' ) then
#> 过程分析的全局列、行和高度层范围
#       setenv PA_BCOL_ECOL "10 90"  # default: all columns 默认：所有列
#       setenv PA_BROW_EROW "10 80"  # default: all rows 默认：所有行
#       setenv PA_BLEV_ELEV "1  4"   # default: all levels 默认：所有层
        setenv PACM_INFILE ${NMLpath}/pa_${MECH}.ctl
        setenv PACM_REPORT $OUTDIR/"PA_REPORT".${YYYYMMDD}
     endif
  endif

#>  综合源解析方法（ISAM）选项
 setenv CTM_ISAM N
 if ( $?CTM_ISAM ) then
    if ( $CTM_ISAM == 'Y' || $CTM_ISAM == 'T' ) then
       setenv SA_IOLIST ${WORKDIR}/isam_control.txt
       setenv ISAM_BLEV_ELEV " 1 1"
       setenv AISAM_BLEV_ELEV " 1 1"

       #> 设置 ISAM 初始条件标志
       if ($NEW_START == true || $NEW_START == TRUE ) then
          setenv ISAM_NEW_START Y
          setenv ISAM_PREVDAY
       else
          setenv ISAM_NEW_START N
          setenv ISAM_PREVDAY "$OUTDIR/CCTM_SA_CGRID_${RUNID}_${YESTERDAY}.nc"
       endif

       #> 设置 ISAM 输出文件名
       setenv SA_ACONC_1      "$OUTDIR/CCTM_SA_ACONC_${CTM_APPL}.nc -v"
       setenv SA_CONC_1       "$OUTDIR/CCTM_SA_CONC_${CTM_APPL}.nc -v"
       setenv SA_DD_1         "$OUTDIR/CCTM_SA_DRYDEP_${CTM_APPL}.nc -v"
       setenv SA_WD_1         "$OUTDIR/CCTM_SA_WETDEP_${CTM_APPL}.nc -v"
       setenv SA_CGRID_1      "$OUTDIR/CCTM_SA_CGRID_${CTM_APPL}.nc -v"

       #> 设置可选的 ISAM 区域文件
       setenv ISAM_REGIONS /work/MOD3EVAL/nsu/isam_v53/CCTM/scripts/input/RGN_ISAM.nc

    endif
 endif

#>  硫追踪模型（STM）
 setenv STM_SO4TRACK N        #>  硫追踪 是否打开[ default: N ]
 if ( $?STM_SO4TRACK ) then
    if ( $STM_SO4TRACK == 'Y' || $STM_SO4TRACK == 'T' ) then
      #> 硫酸盐示踪物归一化选项 [ default: Y ]
      setenv STM_ADJSO4 Y

    endif
 endif

#> CMAQ-DDM-3D （直接敏感性分析方法）选项设置
 setenv CTM_DDM3D N
 set NPMAX    = 1
 setenv SEN_INPUT ${WORKDIR}/sensinput.dat
 setenv DDM3D_HIGH N     # 允许高阶敏感性参数 [ T | Y | F | N ] (default is N/F)

 if ($NEW_START == true || $NEW_START == TRUE ) then
    setenv DDM3D_RST N   # 从重启文件的敏感性场开始 [ T | Y | F | N ] (default is Y/T)
    set S_ICpath =
    set S_ICfile =
 else
    setenv DDM3D_RST Y
    set S_ICpath = $OUTDIR
    set S_ICfile = CCTM_SENGRID_${RUNID}_${YESTERDAY}.nc
 endif

 setenv DDM3D_BCS F      # 嵌套运行时使用敏感性边界条件文件 [ T | Y | F | N ] (default is N/F)
 set S_BCpath =
 set S_BCfile =

 setenv CTM_NPMAX       $NPMAX
 setenv CTM_SENS_1      "$OUTDIR/CCTM_SENGRID_${CTM_APPL}.nc -v"
 setenv A_SENS_1        "$OUTDIR/CCTM_ASENS_${CTM_APPL}.nc -v"
 setenv CTM_SWETDEP_1   "$OUTDIR/CCTM_SENWDEP_${CTM_APPL}.nc -v"
 setenv CTM_SDRYDEP_1   "$OUTDIR/CCTM_SENDDEP_${CTM_APPL}.nc -v"
 setenv CTM_NPMAX       $NPMAX
 setenv INIT_SENS_1     $S_ICpath/$S_ICfile
 setenv BNDY_SENS_1     $S_BCpath/$S_BCfile
 
# =====================================================================
#> 输出文件
# =====================================================================

  #>  设置输出文件名
  setenv S_CGRID         "$OUTDIR/CCTM_CGRID_${CTM_APPL}.nc"         #> 3D Inst. Concentrations  三维瞬时浓度 （CGRID，用于重启）
  setenv CTM_CONC_1      "$OUTDIR/CCTM_CONC_${CTM_APPL}.nc -v"       #> On-Hour Concentrations 整点瞬时浓度
  setenv A_CONC_1        "$OUTDIR/CCTM_ACONC_${CTM_APPL}.nc -v"      #> Hourly Avg. Concentrations 小时平均浓度
  setenv MEDIA_CONC      "$OUTDIR/CCTM_MEDIA_CONC_${CTM_APPL}.nc -v" #> NH3 Conc. in Media 介质中 NH₃ 浓度（双向氨）
  setenv CTM_DRY_DEP_1   "$OUTDIR/CCTM_DRYDEP_${CTM_APPL}.nc -v"     #> Hourly Dry Deposition 小时干沉降量
  setenv CTM_DEPV_DIAG   "$OUTDIR/CCTM_DEPV_${CTM_APPL}.nc -v"       #> Dry Deposition Velocities 干沉降速度
  setenv B3GTS_S         "$OUTDIR/CCTM_B3GTS_S_${CTM_APPL}.nc -v"    #> Biogenic Emissions  生物源排放  
  setenv SOILOUT         "$OUTDIR/CCTM_SOILOUT_${CTM_APPL}.nc"       #> Soil Emissions 土壤信息输出（用于重启）
  setenv CTM_WET_DEP_1   "$OUTDIR/CCTM_WETDEP1_${CTM_APPL}.nc -v"    #> Wet Dep From All Clouds  所有云（解析云+次网格云）的湿沉降
  setenv CTM_WET_DEP_2   "$OUTDIR/CCTM_WETDEP2_${CTM_APPL}.nc -v"    #> Wet Dep From SubGrid Clouds 仅次网格云的湿沉降
  setenv CTM_PMDIAG_1    "$OUTDIR/CCTM_PMDIAG_${CTM_APPL}.nc -v"     #> On-Hour Particle Diagnostics 整点颗粒物诊断
  setenv CTM_APMDIAG_1   "$OUTDIR/CCTM_APMDIAG_${CTM_APPL}.nc -v"    #> Hourly Avg. Particle Diagnostics 小时平均颗粒物诊断
  setenv CTM_RJ_1        "$OUTDIR/CCTM_PHOTDIAG1_${CTM_APPL}.nc -v"  #> 2D Surface Summary from Inline Photolysis 光解二维地表摘要
  setenv CTM_RJ_2        "$OUTDIR/CCTM_PHOTDIAG2_${CTM_APPL}.nc -v"  #> 3D Photolysis Rates   三维光解速率（J-values）
  setenv CTM_RJ_3        "$OUTDIR/CCTM_PHOTDIAG3_${CTM_APPL}.nc -v"  #> 3D Optical and Radiative Results from Photolysis 三维光解光学与辐射结果
  setenv CTM_SSEMIS_1    "$OUTDIR/CCTM_SSEMIS_${CTM_APPL}.nc -v"     #> Sea Spray Emissions 海盐气溶胶排放
  setenv CTM_DUST_EMIS_1 "$OUTDIR/CCTM_DUSTEMIS_${CTM_APPL}.nc -v"   #> Dust Emissions 沙尘排放
  setenv CTM_IPR_1       "$OUTDIR/CCTM_PA_1_${CTM_APPL}.nc -v"       #> Process Analysis 过程分析 （IPR）
  setenv CTM_IPR_2       "$OUTDIR/CCTM_PA_2_${CTM_APPL}.nc -v"       #> Process Analysis 过程分析
  setenv CTM_IPR_3       "$OUTDIR/CCTM_PA_3_${CTM_APPL}.nc -v"       #> Process Analysis 过程分析
  setenv CTM_IRR_1       "$OUTDIR/CCTM_IRR_1_${CTM_APPL}.nc -v"      #> Chem Process Analysis 化学过程分析（IRR）
  setenv CTM_IRR_2       "$OUTDIR/CCTM_IRR_2_${CTM_APPL}.nc -v"      #> Chem Process Analysis 化学过程分析
  setenv CTM_IRR_3       "$OUTDIR/CCTM_IRR_3_${CTM_APPL}.nc -v"      #> Chem Process Analysis 化学过程分析
  setenv CTM_DRY_DEP_MOS "$OUTDIR/CCTM_DDMOS_${CTM_APPL}.nc -v"      #> Dry Dep 干沉降（Mosaic 方案）
  setenv CTM_DRY_DEP_FST "$OUTDIR/CCTM_DDFST_${CTM_APPL}.nc -v"      #> Dry Dep  干沉降（Fast 方案/替代方案）
  setenv CTM_DEPV_MOS    "$OUTDIR/CCTM_DEPVMOS_${CTM_APPL}.nc -v"    #> Dry Dep Velocity  干沉降速度（Mosaic 方案）
  setenv CTM_DEPV_FST    "$OUTDIR/CCTM_DEPVFST_${CTM_APPL}.nc -v"    #> Dry Dep Velocity 干沉降速度（Fast 方案）
  setenv CTM_VDIFF_DIAG  "$OUTDIR/CCTM_VDIFF_DIAG_${CTM_APPL}.nc -v" #> Vertical Dispersion Diagnostic 垂直扩散诊断
  setenv CTM_VSED_DIAG   "$OUTDIR/CCTM_VSED_DIAG_${CTM_APPL}.nc -v"  #> Particle Grav. Settling Velocity 颗粒物重力沉降速度
  setenv CTM_LTNGDIAG_1  "$OUTDIR/CCTM_LTNGHRLY_${CTM_APPL}.nc -v"   #> Hourly Avg Lightning NO 小时平均闪电 NO
  setenv CTM_LTNGDIAG_2  "$OUTDIR/CCTM_LTNGCOL_${CTM_APPL}.nc -v"    #> Column Total Lightning NO  闪电 NO 柱总量
  setenv CTM_VEXT_1      "$OUTDIR/CCTM_VEXT_${CTM_APPL}.nc -v"       #> On-Hour 3D Concs at select sites 选定站点整点三维浓度

  #> 设置 FLOOR 文件（负浓度记录）
  setenv FLOOR_FILE ${OUTDIR}/FLOOR_${CTM_APPL}.txt

  #>  查找现有的日志文件和输出文件
  ( ls CTM_LOG_???.${CTM_APPL} > buff.txt ) >& /dev/null
  ( ls ${LOGDIR}/CTM_LOG_???.${CTM_APPL} >> buff.txt ) >& /dev/null
  set log_test = `cat buff.txt`; rm -f buff.txt

  set OUT_FILES = (${FLOOR_FILE} ${S_CGRID} ${CTM_CONC_1} ${A_CONC_1} ${MEDIA_CONC}         \
             ${CTM_DRY_DEP_1} $CTM_DEPV_DIAG $B3GTS_S $SOILOUT $CTM_WET_DEP_1\
             $CTM_WET_DEP_2 $CTM_PMDIAG_1 $CTM_APMDIAG_1             \
             $CTM_RJ_1 $CTM_RJ_2 $CTM_RJ_3 $CTM_SSEMIS_1 $CTM_DUST_EMIS_1 $CTM_IPR_1 $CTM_IPR_2       \
             $CTM_IPR_3 $CTM_IRR_1 $CTM_IRR_2 $CTM_IRR_3 $CTM_DRY_DEP_MOS                   \
             $CTM_DRY_DEP_FST $CTM_DEPV_MOS $CTM_DEPV_FST $CTM_VDIFF_DIAG $CTM_VSED_DIAG    \
             $CTM_LTNGDIAG_1 $CTM_LTNGDIAG_2 $CTM_VEXT_1 )
  if ( $?CTM_ISAM ) then
     if ( $CTM_ISAM == 'Y' || $CTM_ISAM == 'T' ) then
        set OUT_FILES = (${OUT_FILES} ${SA_ACONC_1} ${SA_CONC_1} ${SA_DD_1} ${SA_WD_1}      \
                         ${SA_CGRID_1} )
     endif
  endif
  if ( $?CTM_DDM3D ) then
     if ( $CTM_DDM3D == 'Y' || $CTM_DDM3D == 'T' ) then
        set OUT_FILES = (${OUT_FILES} ${CTM_SENS_1} ${A_SENS_1} ${CTM_SWETDEP_1} ${CTM_SDRYDEP_1} )
     endif
  endif
  set OUT_FILES = `echo $OUT_FILES | sed "s; -v;;g" `
  ( ls $OUT_FILES > buff.txt ) >& /dev/null
  set out_test = `cat buff.txt`; rm -f buff.txt

  #>  若要求删除，则删除先前输出
  if ( $CLOBBER_DATA == true || $CLOBBER_DATA == TRUE ) then
     echo 
     echo "Existing Logs and Output Files for Day ${TODAYG} Will Be Deleted"

     #>删除先前的日志文件
     foreach file ( ${log_test} )
        echo "Deleting log file: $file"
        /bin/rm -f $file  
     end
 
     #>  删除先前的输出文件
     foreach file ( ${out_test} )
        echo "Deleting output file: $file"
        /bin/rm -f $file  
     end
     /bin/rm -f ${OUTDIR}/CCTM_EMDIAG*${RUNID}_${YYYYMMDD}.nc

  else
     #>  若先前日志文件存在则报错
     if ( "$log_test" != "" ) then
       echo "*** Logs exist - run ABORTED ***"
       echo "*** To overide, set CLOBBER_DATA = TRUE in run_cctm.csh ***"
       echo "*** and these files will be automatically deleted. ***"
       exit 1
     endif
     
     #>  若先前输出文件存在则报错
     if ( "$out_test" != "" ) then
       echo "*** Output Files Exist - run will be ABORTED ***"
       foreach file ( $out_test )
          echo " cannot delete $file"
       end
       echo "*** To overide, set CLOBBER_DATA = TRUE in run_cctm.csh ***"
       echo "*** and these files will be automatically deleted. ***"
       exit 1
     endif
  endif

  #> 运行控制变量
  setenv CTM_STDATE      $YYYYJJJ
  setenv CTM_STTIME      $STTIME
  setenv CTM_RUNLEN      $NSTEPS
  setenv CTM_TSTEP       $TSTEP
  setenv INIT_CONC_1 $ICpath/$ICFILE
  setenv BNDY_CONC_1 $BCpath/$BCFILE
  setenv OMI $OMIpath/$OMIfile
  setenv OPTICS_DATA $OMIpath/$OPTfile
  #> setenv XJ_DATA $JVALpath/$JVALfile
 
  #>  物种定义与光解
  setenv gc_matrix_nml ${NMLpath}/GC_$MECH.nml
  setenv ae_matrix_nml ${NMLpath}/AE_$MECH.nml
  setenv nr_matrix_nml ${NMLpath}/NR_$MECH.nml
  setenv tr_matrix_nml ${NMLpath}/Species_Table_TR_0.nml

  #>  检查光解输入数据
  setenv CSQY_DATA ${NMLpath}/CSQY_DATA_$MECH

  if (! (-e $CSQY_DATA ) ) then
     echo " $CSQY_DATA  not found "
     exit 1
  endif
  if (! (-e $OPTICS_DATA ) ) then
     echo " $OPTICS_DATA  not found "
     exit 1
  endif

# ===================================================================
#>  执行部分
# ===================================================================

  #>  打印可执行文件的属性
  if ( $CTM_DIAG_LVL != 0 ) then
     ls -l $BLD/$EXEC
     size $BLD/$EXEC
     unlimit
     limit
  endif

  #> 将启动对话信息输出到标准输出
  echo 
  echo "CMAQ Processing of Day $YYYYMMDD Began at `date`"
  echo 

  #> Executable call for single PE, uncomment to invoke  单处理器执行调用，取消注释以启用 
  #( /usr/bin/time -p $BLD/$EXEC ) |& tee buff_${EXECUTION_ID}.txt

  #> Executable call for multi PE, configure for your system   多处理器执行调用，请根据您的系统配置   
  #> 以下三行是旧版 mpirun 方案，保持注释
  # set MPI = /usr/local/intel/impi/3.2.2.006/bin64
  # set MPIRUN = $MPI/mpirun
  #( /usr/bin/time -p mpirun -np $NPROCS $BLD/$EXEC ) |& tee buff_${EXECUTION_ID}.txt

  #> 使用 SLURM 的超算集群都配置这个即可
  #( /usr/bin/time -p srun --quiet --mpi=pmi2 -n $NPROCS $BLD/$EXEC ) >& buff_${EXECUTION_ID}.txt
  # 检测是否在 Slurm 环境中
   if ($?SLURM_JOB_ID) then
      echo "检测到 Slurm 环境，作业 ID: $SLURM_JOB_ID"
      echo "使用 srun 自动继承 sbatch 资源分配（不指定 -n）"
      ( /usr/bin/time -p srun --mpi=pmi2 $BLD/$EXEC ) >& buff_${EXECUTION_ID}.txt
   else
      echo "未检测到 Slurm 环境，独立运行"
      echo "手动指定进程数: $NPROCS"
      ( /usr/bin/time -p srun --mpi=pmi2 -n $NPROCS $BLD/$EXEC ) >& buff_${EXECUTION_ID}.txt
   endif
  #> 收集计时输出，以便在下方报告
  set rtarray = "${rtarray} `tail -3 buff_${EXECUTION_ID}.txt | grep -Eo '[+-]?[0-9]+([.][0-9]+)?' | head -1` "
  rm -rf buff_${EXECUTION_ID}.txt

  #> 异常终止时中止脚本
  if ( ! -e $S_CGRID ) then
    echo ""
    echo "**************************************************************"
    echo "** Runscript Detected an Error: CGRID file was not written. **"
    echo "**   This indicates that CMAQ was interrupted or an issue   **"
    echo "**   exists with writing output. The runscript will now     **"
    echo "**   abort rather than proceeding to subsequent days.       **"
    echo "**************************************************************"
    break
  endif

  #>  打印结束文本
  echo 
  echo "CMAQ Processing of Day $YYYYMMDD Finished at `date`"
  echo
  echo "\\\\\=====\\\\\=====\\\\\=====\\\\\=====/////=====/////=====/////=====/////"
  echo

# ===================================================================
#> 完成当日运行并循环至下一日
# ===================================================================

  #> 保存日志文件并进入下一模拟日
  mv CTM_LOG_???.${CTM_APPL} $LOGDIR
  if ( $CTM_DIAG_LVL != 0 ) then
    mv CTM_DIAG_???.${CTM_APPL} $LOGDIR
  endif

  #> 下一模拟日将默认以重启模式运行
  setenv NEW_START false                   #> 这个 CCTM 的设计非常巧妙就在这里，等于每轮循环的第二日模拟都是第一日的重启，所以这里一定是 FALSE

  #>  同时递增公历日和儒略日
  set TODAYG = `date -ud "${TODAYG}+1days" +%Y-%m-%d`     #> 加一天得到明天
  set TODAYJ = `date -ud "${TODAYG}" +%Y%j`               #> Convert YYYY-MM-DD to YYYYJJJ   转换年月日到年积日(儒略日)

end  #> 循环至下一个模拟日            这里和217行构成循环体，也是 CCTM 逐日循环模拟的关键主体

# ===================================================================
#> 生成计时报告
# ===================================================================
set RTMTOT = 0
foreach it ( `seq ${NDAYS}` )
    set rt = `echo ${rtarray} | cut -d' ' -f${it}`
    set RTMTOT = `echo "${RTMTOT} + ${rt}" | bc -l`
end

set RTMAVG = `echo "scale=2; ${RTMTOT} / ${NDAYS}" | bc -l`
set RTMTOT = `echo "scale=2; ${RTMTOT} / 1" | bc -l`

echo
echo "=================================="
echo "  ***** CMAQ TIMING REPORT *****"
echo "=================================="
echo "Start Day: ${START_DATE}"
echo "End Day:   ${END_DATE}"
echo "Number of Simulation Days: ${NDAYS}"
echo "Domain Name:               ${GRID_NAME}"
echo "Number of Grid Cells:      ${NCELLS}  (ROW x COL x LAY)"
echo "Number of Layers:          ${NZ}"
echo "Number of Processes:       ${NPROCS}"
echo "   All times are in seconds."
echo
echo "Num  Day        Wall Time"
set d = 0
set day = ${START_DATE}
foreach it ( `seq ${NDAYS}` )
    #> 设置正确的天数并格式化
    set d = `echo "${d} + 1"  | bc -l`
    set n = `printf "%02d" ${d}`

    #> 选择正确的运行时间变量
    set rt = `echo ${rtarray} | cut -d' ' -f${it}`

    #> 输出一行计时数据
    echo "${n}   ${day}   ${rt}"

    #> 为下一次循环递增日期 
    set day = `date -ud "${day}+1days" +%Y-%m-%d`
end
echo "     Total Time = ${RTMTOT}"
echo "      Avg. Time = ${RTMAVG}"

exit