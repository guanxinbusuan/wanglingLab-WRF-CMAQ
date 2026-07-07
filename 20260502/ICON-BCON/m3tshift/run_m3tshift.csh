#!/bin/csh -f
source $CMAQ_HOME/config_cmaq.csh intel

#> 改成你实际的 m3tshift 路径
set EXEC = /work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/app/mathlib/bin/m3tshift

#> 改成 2024，你的模拟年份
set TARGET_YEAR = 2024

#> 改成你实际的数据目录
set DATADIR = ${CMAQ_DATA}/m3tshift


#> 你已有的原始季节性平均文件名（保持不动）
set AV_CONC_INFILE = CCTM_CONC_v53beta2_intel17.0_HEMIS_cb6r3m_ae7_kmtbr_m3dry_2016_quarterly_av.nc


#> 输出文件名会自动变成 2024
set AV_CONC_OUTFILE = CCTM_CONC_v53beta2_intel17.0_HEMIS_cb6r3m_ae7_kmtbr_m3dry_${TARGET_YEAR}_quarterly_av.nc

setenv INFILE ${DATADIR}/input_files/${AV_CONC_INFILE}
setenv OUTFILE ${DATADIR}/output_files/${AV_CONC_OUTFILE}

#> 第一个时间戳代表前一年的秋季，所以这里减 1
@ TARGET_YEAR = ${TARGET_YEAR} - 1

${EXEC} << EOF
INFILE
2015289
120000
${TARGET_YEAR}289
120000
21960000
131760000
OUTFILE
EOF