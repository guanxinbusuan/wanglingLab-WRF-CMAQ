#!/bin/csh -f 

#=======================================================================
#  Script:  run.mcip
#  Purpose: Runs Models-3/CMAQ Meteorology-Chemistry Interface
#           Processor.  Part of the US EPA's Models-3/CMAQ system.
#  Method:  In UNIX/Linux:  run.mcip >&! mcip.log
#=======================================================================

#-----------------------------------------------------------------------
# 设置MCIP程序的输入输出文件的标识参数
#
#   APPL       = 应用程序名称（用于mcip输出文件名后缀）
#   CoordName  = 坐标系统名称（用于GRIDDESC文件，最多16字符）
#   GridName   = 网格名称描述符（用于GRIDDESC文件，最多16字）每个嵌套域分开操作一次
#   InMetDir   = 输入气象文件所在目录(将wrfout文件软链至此)
#   InGeoDir   = 土地利用分数的文件目录（将geo_em.d*.nc软链至此)
#   OutDir     = MCIP程序输出文件写入的目录
#   ProgDir    = MCIP程序可执行文件所在目录
#   WorkDir    = 工作目录（用于Fortran链接和namelist文件）
#-----------------------------------------------------------------------

source $CMAQ_HOME/config_cmaq.csh intel

set APPL       = 202409
set CoordName  = LamCon_18N_116E    # 16-character maximum
set GridName   = d02_202409       # 16-character maximum

set DataPath   = $CMAQ_DATA
set InMetDir   = $DataPath/wrf
set InGeoDir   = $DataPath/wrf
set OutDir     = $DataPath/mcip/$GridName
set ProgDir    = $CMAQ_HOME/PREP/mcip/src
set WorkDir    = $OutDir

#-----------------------------------------------------------------------
#设置输入气象文件名称
#   文件名必须放在括号内，因为“InMetFiless”是C-shell脚本数组。
#   多个文件名用空格分隔，文件名需要按照时间顺序排列。
#   输入气象文件的最大数目必须小于或等于MAX_MM(在.F源代码里默认367)    
#   示例:
#     set InMetFiles = ( $InMetDir/wrfout_d01_date1 \
#                        $InMetDir/wrfout_d01_date2 ) 每个嵌套域分开操作一次
#  set IfGeo      = "T"           这里决定是否使用WPS生成的下垫面nc文件,最好每个嵌套域都打开
#  set InGeoFile  = $InGeoDir/geo_em.d02.nc   每个嵌套域分开操作一次
#-----------------------------------------------------------------------

set InMetFiles = ( $InMetDir/wrfout_d02_2024-09-04_00:00:00 \
                   $InMetDir/wrfout_d02_2024-09-05_00:00:00 \
                   $InMetDir/wrfout_d02_2024-09-06_00:00:00 \
                   $InMetDir/wrfout_d02_2024-09-07_00:00:00 \
                   $InMetDir/wrfout_d02_2024-09-08_00:00:00 \
                   $InMetDir/wrfout_d02_2024-09-09_00:00:00 )

set IfGeo      = "T"         
set InGeoFile  = $InGeoDir/geo_em.d02.nc

#-----------------------------------------------------------------------
# 设置用户控制选项
#
#   LPV:     0 = 不计算和输出位势涡度
#            1 = 计算和输出位势涡度
#
#   LWOUT:   0 = 不输出垂直速度
#            1 = 输出垂直速度
#
#   LUVBOUT: 0 = 不输出B网格上的u/v风分量
#            1 = 除C网格外，额外输出u/V风分量
#-----------------------------------------------------------------------

set LPV     = 0
set LWOUT   = 0
set LUVBOUT = 1

#-----------------------------------------------------------------------
# 设置运行起止时间和输出间隔 (YYYY-MO-DD-HH:MI:SS.SSSS)
#   MCIP_START:  首个输出日期和时间[UTC]  得夹在InMetFiles的时间当中，cmaq得插值，建议wrfout日期+1 即可;小时不可动，必须0小时
#   MCIP_END:    最后输出日期和时间 [UTC] 这个不用夹在InMetFiles的时间当中，对准wrfout的输出尾巴日期;小时不可动，必须0小时
#   INTVL:       输出频率[minutes]
#-----------------------------------------------------------------------

set MCIP_START = 2024-09-05-00:00:00.0000  # [UTC]
set MCIP_END   = 2024-09-09-00:00:00.0000  # [UTC]

set INTVL      = 60 # [min]

#-----------------------------------------------------------------------
# 选择输出格式
#   1 = Models-3 I/O API 格式
#   2 = netCDF格式
#-----------------------------------------------------------------------

set IOFORM = 1

#-----------------------------------------------------------------------
# 设置移除气象域缓冲网格的方法
# 输出MCIP区域尺寸=气象区域尺寸 - 2*BTRIM - 2*NTHIK -1
# 设置BTRIM=0将使用最大范围的气象输入
#  设置BTRIM=-1将使用X0，Y0，NCOLS，NROWS 指定的窗口
#-----------------------------------------------------------------------

set BTRIM = 0

#-----------------------------------------------------------------------
# 设置MCIP子区域（仅当BTRIM=-1时才使用）
# the following variables will be set automatically from BTRIM and
# size of input meteorology fields.)
#   X0:     输出区域左下角的X坐标（东西方向）最小值1
#   Y0:     输出区域左下角的Y坐标（南北方向）最小值1
#   NCOLS:  输出MCIP区域的列数（不包括MCIP侧边界）
#   NROWS:  输出MCIP区域的行数（不包括MCIP侧边界）
#-----------------------------------------------------------------------

set X0    =  1
set Y0    =  1
set NCOLS =  0
set NROWS = 0

#-----------------------------------------------------------------------
# 设置输出区域诊断打印的单元格坐标
# 如果坐标设为0，将使用区域中心单元格
#-----------------------------------------------------------------------

set LPRT_COL = 0
set LPRT_ROW = 0

#-----------------------------------------------------------------------
# 可选:  设置WRF 兰伯特投影的参考纬度，wps中有
#          如果不设置MCIP将使用两个真纬度的平均值
# 要取消此变量请设置为“-999.0”
#-----------------------------------------------------------------------

set WRF_LC_REF_LAT = -999.0

#=======================================================================
#=======================================================================
#   设置并运行MCIP
#   通常不需要修改下面的内容
#=======================================================================
#=======================================================================

set PROG = mcip

date

#-----------------------------------------------------------------------
# 确保目录存在
#-----------------------------------------------------------------------

if ( ! -d $InMetDir ) then
  echo "No such input directory $InMetDir"
  exit 1
endif

if ( ! -d $OutDir ) then
  echo "No such output directory...will try to create one"
  mkdir -p $OutDir
  if ( $status != 0 ) then
    echo "Failed to make output directory, $OutDir"
    exit 1
  endif
endif

if ( ! -d $ProgDir ) then
  echo "No such program directory $ProgDir"
  exit 1
endif

#-----------------------------------------------------------------------
# 确保输入文件存在
#-----------------------------------------------------------------------

if ( $IfGeo == "T" ) then
  if ( ! -f $InGeoFile ) then
    echo "No such input file $InGeoFile"
    exit 1
  endif
endif

foreach fil ( $InMetFiles )
  if ( ! -f $fil ) then
    echo "No such input file $fil"
    exit 1
  endif
end

#-----------------------------------------------------------------------
# Make sure the executable exists.
#-----------------------------------------------------------------------

if ( ! -f $ProgDir/${PROG}.exe ) then
  echo "Could not find ${PROG}.exe"
  exit 1
endif

#-----------------------------------------------------------------------
# Create a work directory for this job.
#-----------------------------------------------------------------------

if ( ! -d $WorkDir ) then
  mkdir -p $WorkDir
  if ( $status != 0 ) then
    echo "Failed to make work directory, $WorkDir"
    exit 1
  endif
endif

cd $WorkDir

#-----------------------------------------------------------------------
# Set up script variables for input files.
#-----------------------------------------------------------------------

if ( $IfGeo == "T" ) then
  if ( -f $InGeoFile ) then
    set InGeo = $InGeoFile
  else
    set InGeo = "no_file"
  endif
else
  set InGeo = "no_file"
endif

set FILE_GD  = $OutDir/GRIDDESC

#-----------------------------------------------------------------------
# Create namelist with user definitions.
#-----------------------------------------------------------------------

set MACHTYPE = `uname`
if ( ( $MACHTYPE == "AIX" ) || ( $MACHTYPE == "Darwin" ) ) then
  set Marker = "/"
else
  set Marker = "&END"
endif

cat > $WorkDir/namelist.${PROG} << !

 &FILENAMES
  file_gd    = "$FILE_GD"
  file_mm    = "$InMetFiles[1]",
!

if ( $#InMetFiles > 1 ) then
  @ nn = 2
  while ( $nn <= $#InMetFiles )
    cat >> $WorkDir/namelist.${PROG} << !
               "$InMetFiles[$nn]",
!
    @ nn ++
  end
endif

if ( $IfGeo == "T" ) then
cat >> $WorkDir/namelist.${PROG} << !
  file_geo   = "$InGeo"
!
endif

cat >> $WorkDir/namelist.${PROG} << !
  ioform     =  $IOFORM
 $Marker

 &USERDEFS
  lpv        =  $LPV
  lwout      =  $LWOUT
  luvbout    =  $LUVBOUT
  mcip_start = "$MCIP_START"
  mcip_end   = "$MCIP_END"
  intvl      =  $INTVL
  coordnam   = "$CoordName"
  grdnam     = "$GridName"
  btrim      =  $BTRIM
  lprt_col   =  $LPRT_COL
  lprt_row   =  $LPRT_ROW
  wrf_lc_ref_lat = $WRF_LC_REF_LAT
 $Marker

 &WINDOWDEFS
  x0         =  $X0
  y0         =  $Y0
  ncolsin    =  $NCOLS
  nrowsin    =  $NROWS
 $Marker

!

#-----------------------------------------------------------------------
# 设置Fortran单元链接
#-----------------------------------------------------------------------

rm fort.*
if ( -f $FILE_GD ) rm -f $FILE_GD

ln -s $FILE_GD                   fort.4
ln -s $WorkDir/namelist.${PROG}  fort.8

set NUMFIL = 0
foreach fil ( $InMetFiles )
  @ NN = $NUMFIL + 10
  ln -s $fil fort.$NN
  @ NUMFIL ++
end

#-----------------------------------------------------------------------
# 设置输出文件名和环境变量
#-----------------------------------------------------------------------

setenv IOAPI_CHECK_HEADERS  T
setenv EXECUTION_ID         $PROG

setenv GRID_BDY_2D          $OutDir/GRIDBDY2D_${APPL}.nc
setenv GRID_CRO_2D          $OutDir/GRIDCRO2D_${APPL}.nc
setenv GRID_DOT_2D          $OutDir/GRIDDOT2D_${APPL}.nc
setenv MET_BDY_3D           $OutDir/METBDY3D_${APPL}.nc
setenv MET_CRO_2D           $OutDir/METCRO2D_${APPL}.nc
setenv MET_CRO_3D           $OutDir/METCRO3D_${APPL}.nc
setenv MET_DOT_3D           $OutDir/METDOT3D_${APPL}.nc
setenv LUFRAC_CRO           $OutDir/LUFRAC_CRO_${APPL}.nc
setenv SOI_CRO              $OutDir/SOI_CRO_${APPL}.nc
setenv MOSAIC_CRO           $OutDir/MOSAIC_CRO_${APPL}.nc

if ( -f $GRID_BDY_2D ) rm -f $GRID_BDY_2D
if ( -f $GRID_CRO_2D ) rm -f $GRID_CRO_2D
if ( -f $GRID_DOT_2D ) rm -f $GRID_DOT_2D
if ( -f $MET_BDY_3D  ) rm -f $MET_BDY_3D
if ( -f $MET_CRO_2D  ) rm -f $MET_CRO_2D
if ( -f $MET_CRO_3D  ) rm -f $MET_CRO_3D
if ( -f $MET_DOT_3D  ) rm -f $MET_DOT_3D
if ( -f $LUFRAC_CRO  ) rm -f $LUFRAC_CRO
if ( -f $SOI_CRO     ) rm -f $SOI_CRO
if ( -f $MOSAIC_CRO  ) rm -f $MOSAIC_CRO

if ( -f $OutDir/mcip.nc      ) rm -f $OutDir/mcip.nc
if ( -f $OutDir/mcip_bdy.nc  ) rm -f $OutDir/mcip_bdy.nc

#-----------------------------------------------------------------------
# Execute MCIP.
#-----------------------------------------------------------------------

$ProgDir/${PROG}.exe

if ( $status == 0 ) then
  rm fort.*
  exit 0
else
  echo "Error running $PROG"
  exit 1
endif