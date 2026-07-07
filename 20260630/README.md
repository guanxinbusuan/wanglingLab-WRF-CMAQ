# WRF-CMAQ 20260630 实验
- 操作于 20260630 —— 20260707


## 实验内容
WRF-CMAQ 20260630 实验是基于 WRF-CMAQ 20260620 实验的外拓，即成功运行出 d02 嵌套域的 CMAQ 模拟后，同理运行延申到 d03 嵌套域的 CMAQ 模拟。


## 实验目的
1. 利用  WRF-CMAQ 202620 实验的实验结果 （成功嵌套d01的ICON/BCON 的 d02 的 CCTM 和 MCIP 输出），进行第三级嵌套(d03域)的CCTM模拟试验；
2. 确认自己设计出的 CMAQ 操作流是否可用于第三级(第三层)嵌套，如若确认成功，整个模型链即可投入正式论文实验的生产环境






## 实验流程--WRF部分
> 因为WRF体系的数值模式都是two-way-nesting设计思路，其d01/d02/d03的模拟结果都是一锅出，只是因为CMAQ是one-way-nesting设计思路,从MCIP步骤开始都是逐个嵌套域的单独操作，所以两个嵌套域即可通过ICON/BCON将输出结果链接进行嵌套式spin-up

此步骤和 WRF-CMAQ 20260502 实验的 WRF部分实验流程一模一样，且因为WRF体系的数值模式都是two-way-nesting设计，所以和 WRF-CMAQ 20260502 实验共用完全同样的 WRF 模拟设置、实验操作流和输出结果文件。








## 实验流程--CMAQ部分
### MCIP使用流程

- MCIP需要根据每个嵌套区域单独操作，WRF-CMAQ 20260502 实验只操作了d01嵌套域 / WRF-CMAQ 20260620 实验只操作了d02嵌套域，所以本次 WRF-CMAQ 20260630 实验需要操作 d03 嵌套域
- 记得运行前先把需要执行 mcip 的嵌套域的 wrfout 文件和 geo_em 文件软链接到 run_mcip.csh 所需的 InMetDir/InGeoDir 目录中

> Tips:
> > csh脚本无法直接在bash中兼容，如果希望所有环境变量都在当前交互 shell 中生效，建议切换到 tcsh

***总结workflow如下:*** 直接登录节点终端执行，MCIP是单核串行程序
```bash
#先bash执行
#清理module环境
module purge  
#激活依赖与环境变量路径设置
source /work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/scripts/env.sh
#查看关键环境变量
echo ${CMAQ_HOME} ${CMAQ_DATA}

#再切换tcsh并执行
tcsh
#查看切换tcsh后env.sh脚本的环境变量是否能用（可选）
echo ${CMAQ_HOME} ${CMAQ_DATA} 
#激活CMAQ的设置脚本（可选）
source $CMAQ_HOME/config_cmaq.csh intel

#回到 mcip 的脚本目录（可选）
cd $CMAQ_HOME/PREP/mcip/scripts
#运行程序脚本 run_mcip.sh
./run_mcip_d03.csh >&! mcip_d03.log
```
PS：在我的超算环境中，我已通过env.sh脚本硬编码了两个关键环境变量
```bash
export CMAQ_HOME=/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/app
export CMAQ_DATA=/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/case/data
```

- 记得把 MCIP 的11个输出文件中 `GRIDCRO2D_202409.nc、LUFRAC_CRO_202409.nc、METCRO3D_202409.nc` 这3个nc文件拷贝到 Windows本地，放在工程目录下的 `mcip/mcip-out/${domains}/` 的相应目录，方便分离式的本地操作生成真正可输入 CMAQ 的排放清单文件；

- 注意放在相应的`$domains`目录下，别放错了!




### MIX_to_CMAQ操作流程
**Tips 20260629**:
- 借助 reasonix (AI-Agaent-CLI 工具) 已经将原本 `daymixtocmaq.py` 脚本的back版本重构升级为 `daymixtocmaq-v3.py` 的v3版本，速度更快，性能更好；经测试, 其输出文件可以被CCTM读取且对模拟结果无影响!

> 转换脚本 `daymixtocmaq-v3.py` 使用命令：
- 记得指定 domain 和 format 参数(domian根据mcip的输出定(最好每个嵌套域分离式操作)，format推荐统一用nc3)

```cmd
python daymixtocmaq-v3.py d01 --format nc3
python daymixtocmaq-v3.py d02 --format nc3
python daymixtocmaq-v3.py d03 --format nc3
```
PS:我的CMAQ执行流是做了分离式设计，所以这个操作是在Windows本地笔记本完成的




### wrfbiochemi_to_cmaq操作流程
1. 先在超算环境中操作
```bash
# 回到wrfchem中部署的 megan_bio_emiss 插件目录
cd /work/home/wangling02/apprepo/wrfchem/4.3-intelmpi2017/app/megan_bio_emiss
module purge
source env.sh
cd ./20260528
# 运行生成 wrfbiochemi*.nc 文件,该文件包含了基于BEIS算法的排放因子和参数,
# 这个因子可用于生成cmaq内置的BEIS在线计算生物排放模型的排放潜力文件（B3GRD）
./megan_bio_emiss < megan_bio_emiss.inp > megan_bio_emiss.out
```   
PS:需要将超算输出的 wrfbiochemi_d0* (记得对应嵌套域) nc文件放到Windows本地笔记本的工程目录的 wrfbiochemi_to_cmaq 目录下(无需 `$domains` 子目录)

2. 然后在Windows本地笔记本运行转换脚本生成运行CMAQ必须的B3GRD文件
> 转换脚本 `wrfbiochemi_to_b3grd.py` 使用命令：
>- **Tips 20260706 :**
> 通过reasonix (AI-Agaent-CLI 工具) 已经将原本 `wrfbiochemi_to_b3grd.py` 脚本的原始版本重构升级为 `wrfbiochemi_to_b3grd-v2.py` 的v2版本

- 记得指定 domain (根据mcip的输出定(最好每个嵌套域分离式操作)) 参数和  <夏季月>  <冬季月> 参数(和meagn_bio_emiss.inp设置的起始月有关系)
```cmd
python wrfbiochemi_to_b3grd.py d01 7 1 
python wrfbiochemi_to_b3grd.py d02 7 1 
python wrfbiochemi_to_b3grd-v2.py d03 8 1 
```
PS:我的CMAQ执行流是做了分离式设计，所以这个操作是在超算环境和Windows本地笔记本环境所共同完成的，






### ICON-BCON操作流程
用d02嵌套域的CCTM输出文件（对应icon/bcon的regrid模式启动）制作d03的IC/BC场文件;

**Tips:**
- 本次实验的这个操作步骤和WRF-CMAQ 20260502 实验用CMAS官方CMAQ季节性平均半球输出文件做icon/bcon的regrid模式启动的操作步骤**非常不同**，尤其是bcon的反复运行操作


#### icon操作流程
ICON程序是不覆写的（程序源代码写定的就是尾行加入模式，而非覆写模式），故icon只运行一次即可,对齐模拟开始时间制作IC场文件
>参考 WRF-CMAQ 20260502 第二个实验日志，第三点

***总结workflow如下:*** 直接登录节点终端执行，icon是单核串行程序
```bash
#先bash执行
#清理module环境
module purge  
#激活依赖与环境变量路径设置
source /work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/scripts/env.sh
#查看关键环境变量
echo ${CMAQ_HOME} ${CMAQ_DATA}

#再切换tcsh并执行
tcsh
#查看切换tcsh后与激活设置脚本后的环境变量是否能用（可选）
echo ${CMAQ_HOME} ${CMAQ_DATA} 
#激活CMAQ的设置脚本（可选）
source $CMAQ_HOME/config_cmaq.csh intel

#回到 icon 的脚本目录（可选）
cd $CMAQ_HOME/PREP/icon/scripts
#运行程序脚本 run_icon.csh
./run_icon_d03.csh >&! icon_d03.log
```




#### bcon操作流程
BCON程序也是不覆写的（程序源代码写定的就是尾行加入模式，而非覆写模式），原来目的就是在这里等着呢！
>参考 WRF-CMAQ 20260502 第二个实验日志，第三点

- **反复运行bcon才能让d02的CCTM输出文件完整覆盖d03模拟时间，也才能制作完整模拟时间的BC场文件**


***总结workflow如下:*** 直接登录节点终端执行，bcon是单核串行程序
```bash
#先bash执行
#清理module环境
module purge  
#激活依赖与环境变量路径设置
source /work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/scripts/env.sh
#查看关键环境变量
echo ${CMAQ_HOME} ${CMAQ_DATA}

#再切换tcsh并执行
tcsh
#查看切换tcsh后与激活设置脚本后的环境变量是否能用（可选）
echo ${CMAQ_HOME} ${CMAQ_DATA} 
#激活CMAQ的设置脚本（可选）
source $CMAQ_HOME/config_cmaq.csh intel

#回到 bcon 的脚本目录（可选）
cd $CMAQ_HOME/PREP/bcon/scripts
#运行程序脚本 run_bcon.csh
./run_bcon_d03.csh >&! bcon_d03.log
```
PS:
1. 反复运行bcon的csh脚本，但每次只需要修改csh脚本中的 DATE 变量（会自动匹配到相应文件，就能完整覆盖完整模拟时间）,本次实验是将`set DATE = "2024-09-05"` 每次反复运行操作都是加一天，直到完成运行`set DATE = "2024-09-08"`
2. icon可以不取消SDATE和STIME的注释，但是bcon的SDATE、STIME、RUNLEN的注释必须都取消，但反复运行时无需修改此三变量








### CCTM操作流程
按照上述步骤生成d03嵌套域的输入IC/BC场文件，人为/生物排放清单文件后:
- 根据相应的路径和名称对run_cctm_d02.csh执行脚本中的d02相关文件和信息进行修改，包括`APPL,NPCOL/NPROW,GRID_NAME`等关键环境变量以及文件名（`IC/BC + 人为/生物清单`）等，但是，一定不能破坏核心的CCTM的日循环模拟逻辑！

***总结workflow如下:*** 提交到超算集群的计算节点并行执行积分任务，CCTM是多节点多MPI并行程序
```bash
# 根据需求调整好 run_cctm.csh 这个核心脚本的设置 
#请务必理解清楚了 run_cctm.csh 的 CCTM 的逐日模拟循环逻辑
cd $CMAQ_HOME/CCTM/scripts
vim run_cctm_d03.csh

#回到 slurm 脚本目录进行提交
cd $CMAQ_DATA/..
sbatch cmaq_d03.slurm
```
PS: *20260706* 成功解决了 CMAQ-CCTM-BEIS 在线生物排放的 LAI 值异常问题，详情可见 WRF-CMAQ 20260630 实验的第二个实验日志！










------------------------------------------------------------------------------------------------------------------------

## 实验日志
记录于 2026-06-30 02:17:00  

关于CMAQ的CCTM的MPI并行的网格分解方案，这里给个AI-Chat的prompt提示词：
```Prompt
    CMAQ 要求二维域分解必须整除网格吗？有余数不可以吗？
    NX = 151
    NY = 127
    如果我有189个核可调度呢，不一定要使用全部核数,请给出最优分配核数的方案（NPCOL X NPROW） 
```

- 更新于 2026-06-30 02:30:00  





## 实验日志
记录于 2026-06-30 05:27:00  

关于开启生物排放的 CMAQ-BEIS3 的 LAI 异常问题报错：
d03区域模拟的生物排放有问题，暂时关闭了d03的生物排放，避免触发这个 CMAQ-BEIS3 的 LAI 异常问题
```txt
#开启生物排放时的报错显示:
     Value for PROMPTFLAG:  F returning FALSE
     NOTE: Grid settings initialized using MET_CRO_2D in  
          gridded file GRID NAME: d03_202409_CROSS
      
     "B3GTS_S" opened as NEW(READ-WRITE )
     File name "/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/app/../case/data/cctm/output_CCTM_v532_intel_d03_202409/CCTM_B3GTS_S_v532_intel_d03_202409_20240905.nc"
     File type GRDDED3 
     Execution ID "CMAQ_CCTMv532_wangling02_20260629_203411_165604228"
     Grid name "d03_202409"
     Dimensions: 127 rows, 151 cols, 1 lays, 22 vbles
     NetCDF ID:   1114112  opened as VOLATILE READWRITE  
     Starting date and time  2024249:010000 (1:00:00   Sept. 5, 2024)
     Timestep                          010000 (1:00:00 hh:mm:ss)
     Maximum current record number         0
     >>> Processing Thursday Sept. 5, 2024
          Temporal BEIS at time 0:00:50
     
     *** ERROR ABORT in subroutine BEIS3
      LAI=********** out of range at (C,R)=  1,  2
     Date and time  0:00:50   Sept. 5, 2024   (2024249:000050)
```

ncdump/nco 查看了mcip 输出的 METCROD2D 文件中LAI变量，未发现缺测值或异常值啊，这就有点奇怪了.......

初步推测，问题应该在本地windows制作的B3GRD_d03.nc 文件上；


**测试笔记 20260705-20260706:**
排除METCROD2D文件中LAI变量问题后，试图检查B3GRD_d03.nc文件的是否真的存在问题，并进行修复与重新CCTM模拟。

OK,借助 Reasonix这个 AI-Agent-CLI 成功破案：
> 这个LAI值异常确实来源于B3GRD文件的LAI_ 前缀变量，通过重构 wrfbiochemi_to_b3grd.py 升级为 wrfbiochemi_to_b3grd-v2.py 发现真正的问题不是这个生成脚本的问题，而是该脚本所需的输入的wrfbiochemi_* 文件中的 MLAI 变量就已经是有问题（只有8~9月两个月是正确值）的，特别是在 生长月(夏季)/非生长月(冬季) 出现了明显的非LAI值


所以给出解决方案是：
修改并运行 `wrfbiochemi_to_cmaq\wrfchem\megan_bio_emiss\megan_bio_emiss.inp` 文件的`start_lai_mnth`变量值为01，`end_lai_mnth`变量值为12，重新让wrfchem的megan插件读取并生成完整的 01~12 月的LAI数值


- 更新于 2026-07-06 03:30:00








## 实验日志
记录于 2026-07-07 01:20:00  

1. CCTM 模拟在MIX_to_cmaq 的 fangda 系数在默认 1.2 的设置时， d03模拟的ACONC数量级系统性偏低,需要开始测试更加合适的、非默认的全局放大系数 fangda 值

**测试笔记 20260706-20260707:**
> 经测试发现 fangda = 10.8 ~ 12 ~ 15.6 区间范围内，CCTM模拟的数量级会被放大到更加合理的区间(仅限于当前实验的d03嵌套域模拟)

2. 发现了个很有意思的 CCTM 模拟加速细节

- 重新运行cctm模拟的速度远快于覆盖原本cctm输出的模拟速度

意思就是每次sbatch提交任务进行CCTM积分前,需要删除之前运行有的 `${CMAQ_DATA}/cctm/output_CCTM_${VRSON}` 目录（ *对应当前嵌套域的cctm输出目录，千万别删错了！！！* ），这样能大幅度加速CCTM模拟运行的速度，推测是nc3文件格式的覆写性能约束。

- 更新于 2026-07-07 01:50:00  

--------------------------------------------------------------------------------------------------------------------------------