# WRF-CMAQ 20260502 实验
- 操作于 20260528 —— 20260612


## 实验内容
利用刘老师给的 WRF - daymixtocmaq - wrfbiochemitocmaq - CMAQ 的模型链方案，运行一次不嵌套的 d01 域的（MIX离线清单 + BEIS在线生物排放）空气质量模拟 


## 实验目的
1. 利用WPS(WRF)的 20260502 实验结果(wrfout：utc2024090400——utc2024090900)，学习如何使用与设置MCIP程序，生成CMAQ的11个关键网格文件(含2d/3d气象场文件)
2. 开发一个类似于SMOKE的程序,生成CMAQ可读取的MIX清单的通量文件
3. 联合wrfchem的megan_bio_emiss的插件，利用其生成的wrfbiochemi文件再生成cmaq可用的B3GRD文件
4. 学习如何使用与设置ICON/BCON程序，生成CMAQ的热启动IC/BC场文件
5. 理解并学会如何设置CCTM的运行csh脚本,调整slurm脚本并提交


## 实验流程--WRF部分
### WPS实验流程
编辑好namelist.wps文件，直接登录节点执行（都是串行程序）：

解码气象资料 -----> 静态地理插值   -----> 生成 met_em*文件
``` bash
#软链接一个解码气象资料的变量映射表
ln -sf ungrib/Variable_Tables/Vtable.GFS Vtable
#创建一系列特定命名的符号链接
./link_grib.csh ../FNL_0p25_MOJIE/*.grib2
#解码原始气象资料
./ungrib.exe
#生成静态地理网格
./geogrid.exe
#气象资料插值静态地理网格
./metgrid.exe
```
PS:WPS生成的geo_em.d*.nc文件软链接至MCIP所需的InGeoDir目录中


### WRF实验流程
编辑好namelist.input文件,并行程序需要sbatch提交slurm多节点调度系统:

生成初始场/侧边界场/同化场  ----> 提交自动化脚本，wrf开始积分
``` bash
#real初始化
sbatch real_slurm.slurm
#清除残留的real执行生成的日志文件
rm -rf ./rsl.error.* rsl.out.*

#自动化脚本 monitor_wrfarw.sh  
#该脚本可自动sbatch wrf_slurm.slurm 并监测 wrf 积分是否卡死
#执行权限
chmod +x monitor_wrfarw.sh
#静默化提交与后台执行
nohup ./monitor_wrfarw.sh > /dev/null 2>&1 &
```
PS:WRF生成wrfout文件后软链接至MCIP所需的InMetDir中



这个WPS和WRF步骤都是运行WRF-ARW模型，用于离线式给CMAQ提供气象场网格，但是WRF体系的数值模式都是two-way-nesting设计思路，其d01/d02/d03的模拟结果都是一锅出，但CMAQ却是one-way-nesting设计思路,从MCIP步骤开始都是逐个嵌套域的单独操作，两个嵌套域即可通过ICON/BCON将输出结果链接进行嵌套式spin-up!







## 实验流程--CMAQ部分
### MCIP使用流程
MCIP是WRF和CMAQ的架通桥梁，也是离线气象-化学耦合的关键,主要将WRF的3d网格转换到CMAQ可用的3d网格（有部分变形和裁剪）

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
./run_mcip.csh >&! mcip.log
```
PS：在我的超算环境中，我已通过env.sh脚本硬编码了两个关键环境变量
```bash
export CMAQ_HOME=/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/app
export CMAQ_DATA=/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/case/data
```

- 记得把 MCIP 的11个输出文件中 `GRIDCRO2D_202409.nc、LUFRAC_CRO_202409.nc、METCRO3D_202409.nc` 这3个nc文件拷贝到 Windows本地，放在工程目录下的 `mcip/mcip-out/${domains}/` 的相应目录，方便分离式的本地操作生成真正可输入 CMAQ 的排放清单文件。




### MIX_to_CMAQ操作流程

**利用MIX清单数据库（路径: MIX_to_cmaq/MIX/MIX{month} ）处理并插入MCIP的输出网格,生成CCTM真正可读取的排放清单nc3文件**

> 转换脚本 `daymixtocmaq.py` 使用命令：
- 记得指定 domain 和 format 参数(domian根据mcip的输出定(最好每个嵌套域分离式操作)，format推荐统一用nc3)
```cmd
python daymixtocmaq.py d01 --format nc3
python daymixtocmaq.py d02 --format nc3
python daymixtocmaq.py d03 --format nc3
```
PS:我的CMAQ执行流是做了分离式设计，所以这个操作是在Windows本地笔记本完成的







### wrfbiochemi_to_cmaq操作流程
CMAQ V5.3在线生物排放计算依赖于内置的BEIS模型，该模型需要输入一个B3GRD的参数文件用于存储：植被在标准条件下的排放强度，土地利用信息和LAI，土壤NO基准值；
CMAQ运行时会根据实际温度和光强，通过调节因子（如温度响应函数、光响应函数）动态计算最终排放。这种分离使得一个B3GRD文件可以用于全年不同气象条件下的模拟。

1. 先在超算环境中操作
```bash
# 回到wrfchem中部署的 megan_bio_emiss 插件目录
cd /work/home/wangling02/apprepo/wrfchem/4.3-intelmpi2017/app/megan_bio_emiss
module purge
source env.sh
cd ./20260502
# 运行生成 wrfbiochemi*.nc 文件,该文件包含了基于BEIS算法的排放因子和参数,
# 这个因子可用于生成cmaq内置的BEIS在线计算生物排放模型的排放潜力文件（B3GRD）
./megan_bio_emiss < megan_bio_emiss.inp > megan_bio_emiss.out
```   

2. 然后在Windows本地笔记本运行转换脚本生成运行CMAQ必须的B3GRD文件：
> 转换脚本 `wrfbiochemi_to_b3grd.py` 使用命令：
- 记得指定 domain (根据mcip的输出定(最好每个嵌套域分离式操作)) 参数和  <夏季月>  <冬季月> 参数(推荐统一用 7 和 1)
```cmd
python wrfbiochemi_to_b3grd.py d01 7 1 
python wrfbiochemi_to_b3grd.py d02 7 1 
python wrfbiochemi_to_b3grd.py d03 7 1 
```
PS:我的CMAQ执行流是做了分离式设计，所以这个操作是在超算环境和Windows本地笔记本环境所共同完成的










### ICON-BCON操作流程
> - 如果希望d01嵌套域像wrfchem一样真正的热启动（其实就是ICON/BCON工具的regrid模式启动），就得用我下载的CMAQ官方给的季节性平均半球 CMAQ 输出文件进行时间偏移。
> - profile模式启动ICON/BCON的话是从csv文件启动的（太平洋理想干净剖面的垂直轮廓线）

CCTM_CONC_v53beta2_intel17.0_HEMIS_cb6r3m_ae7_kmtbr_m3dry_2016_quarterly_av.nc就是官方给的季节性平均半球 CMAQ 输出文件，使用m3tshift工具进行时间偏移，生成新的输入文件供ICON/BCON工具使用。这个文件很特殊，是特制的“全功能大礼包”（浓度 + 气象高度合二为一），专门用来启动最外层的d01，因为icon/bcon的regrid模式启动额外需要粗网格（外域）的浓度cctm输出文件 + 气象mcip输出文件。

**参考**:
- [CMAS官方对于CMAQ季节性平均半球输出文件的说明](https://github.com/USEPA/CMAQ/blob/main/DOCS/Users_Guide/Tutorials/CMAQ_UG_tutorial_HCMAQ_IC_BC.md)



#### m3tshift操作流程
给官方的CMAQ季节性平均半球输出文件进行时间偏移，这样对于d01嵌套域ICON-BCON才能用regrid模式启动
> Tips:
> > CMAq基本都是csh脚本驱动所以其各个子流程操作和MCIP使用流程类似

***总结workflow如下:*** 直接登录节点终端执行，m3tshift是单核串行程序
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

#回到 m3tshift 的脚本目录（可选）
cd $CMAQ_DATA/m3tshift
#运行程序脚本 run_m3tshift.csh
./run_m3tshift.csh >&! m3tshift.log
```
PS：
1. 日志文件m3tshift.log报错无所谓,偏移后的nc文件正常生成即可(因为m3tshfit.exe会自动找时间戳，但时间戳是有限的)
2. m3tshift工具进行时间偏移只需要年份偏移即可，具体模拟日期偏移可以靠ICON/BCON智能插值（不需要、也不可能让 m3tshift 生成 9 月 4 日这样的具体日期）




#### icon操作流程
生成CCTM积分的目标嵌套域的IC文件
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
./run_icon.csh >&! icon.log
```



#### bcon操作流程
生成CCTM积分的目标嵌套域的BC文件，其设置和icon的设置非常对称
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
./run_bcon.csh >&! bcon.log
```










### CCTM操作流程
CCTM才是真正的积分程序，也是CMAq的主程序，其地位类似于WRF模式中的最后一步slurm并行运行wrf.exe
***总结workflow如下:*** 提交到超算集群的计算节点并行执行积分任务，CCTM是多节点多MPI并行程序
```bash
# 根据需求调整好 run_cctm.csh 这个核心脚本的设置 
#请务必理解清楚了 run_cctm.csh 的 CCTM 的逐日模拟循环逻辑
cd $CMAQ_HOME/CCTM/scripts
vim run_cctm.csh

#回到 slurm 脚本目录进行提交
cd $CMAQ_DATA/..
sbatch cmaq.slurm
```
**参考**:
1. [run_cctm.csh设置的在线官方文档-Github](https://github.com/USEPA/CMAQ/blob/main/DOCS/Users_Guide/CMAQ_UG_ch06_model_configuration_options.md#6.10_Gas_Phase_Chem)
2. [cctm模式设置选项-GitHub](https://github.com/USEPA/CMAQ/blob/main/DOCS/Users_Guide/Appendix/CMAQ_UG_appendixA_model_options.md#Syn_time_Option)










## 实验日志

记录于 2026-05-29 7:25:00  

**吸取教训,血泪经验：**
<u>1. MCIP不支持WPS中truelat1=truelat2的投影坐标系，所以WPS-WRF必须为truelat1/2不相等的投影坐标系的输出wrfout文件；</u>

<u>2. MCIP内部需要对wrfout文件进行插值，所以MCIP_START必须得在wrfout文件时间当中(留下插值空间),MCIP_END好像不用（请参考后文的“掐头去尾”原则）；</u>

<u>3. MCIP必须生成LUFRAC_CRO_202409.nc文件！</u>

- 更新于 2026-06-02 16:59:00 
---------------------------------------------------------------------------------------------------------------------------------






## 实验日志

记录于 2026-06-05 11:21:00  

**吸取教训,血泪经验：**
<u>1. CCTM模拟时刻和MCIP的时间设置要对应（两者和排放清单文件的第一个积分步必须 日期+时间 双双对齐，后面逐日循环模拟无所谓，但一开始必须对齐），但是比起 WRF 最保险的方案还是“掐头去尾” </u>

2. CCTM设置的
```csh
set STTIME     = 000000            #> 起始 GMT 时间（HHMMSS，时分秒格式）  模拟开始的小时时刻 其实按照这一套流程，这里只能是0小时
set NSTEPS     = 240000            #> 在逐日循环中，每一天的 NSTEPS 应该只跑 24 小时。 其实按照这一套循环模拟流程，这里也不能动
set TSTEP      = 010000            #> 输出时间步长间隔（HHMMSS，时分秒格式） 隔多久写出一帧 
```
<u>绝对不能动 ！！！！ 尤其 STTIME 必须是00000  ！！！！！ （0小时时刻才能配合 `daymixtocmaq.py` 生成的排放清单文件）；NSTEPS 也必须是 24 小时才能配合 run_cctm.csh 脚本里写定的日循环逻辑  !!!! 得嘞，TSTEP 也是个不能动的大爷，这是很多输入文件的固有属性，动了会报错退出，因为对不齐！！！！！ </u>

<u>3. 重新运行ICON/BCON 必须删除原来的 ICON/BCON 的输出文件    !!!!! 
他喵的这两个程序无法覆写 (应该是源代码设置的尾行加入模式，而非覆写模式)，会导致CCTM模拟的IC/BC错位！</u>

- 暂存测试笔记:
我现在测试一下 如果MCIP_END设置为23小时（日期不变）是否能在这个流程下完整跑通，尤其是对于 `daymixtocmaq.py` 生成的排放清单文件是否能实现 CCTM 的逐日模拟下的儒略日（年积日）的24h排放模板循环

 好吧，压根不行，必须严格遵守“掐头去尾”原则！！！

- 更新于 2026-06-06 15:29:00 
---------------------------------------------------------------------------------------------------------------------------------








## 实验日志

记录于 2026-06-06 20:07:00  

**吸取教训,血泪经验：**
1. CCTM设置的
```csh
 set START_DATE = "2024-09-05"     #> 开始日期
 set END_DATE   = "2024-09-08"     #> 结束日期
```
他喵的，CMAQ的时间设置真是个天坑！！！ 
这两个CCTM设置的开始日期和结束日期是包含自身0-23小时的，所以真正的“掐头去尾”原则就是：
    wrfout输出的一个日期这一天+1 的零时设置为 MCIP的开始时间 set MCIP_START = 2024-09-05-00:00:00.0000 ，必须连同时刻（0小时时刻）与日期在内的时间戳与 `daymixtocmaq.py` 生成的排放清单完全相等（过了这一天无所谓，可以成功开启儒略日循环）！！！！而wrfout的输出尾巴日期则可以为MCIP的结束时间set MCIP_END   = 2024-09-09-00:00:00.0000  （不能动小时！！！），但这时候CCTM的START_DATE和END_DATE就只能，且必须指定为包含自身24小时的5号和8号！！！！！！！！！！

> 踩坑教训

2. 每个人搭建出的 CMAQ 流程都不一样，我这一套是独属于我自己的 WRF-daymixtocmaq-CMAQ 模型！所以：
***掐头去尾：如上第一点所叙述；
 尾巴对准，MCIP设置的0小时千万不能动（MCIP_START和MCIP_END都只能是0小时，千万别自作主张改成别的小时，别的任何小时都不行，切记！！！！！）***


1. 必须详细理解我归纳的这个时间设置原则，因为本质上就是 wrfout 、 MCIP 、daymixtocmaq 、CCTM 这几个核心的环节时间对齐问题；尤其是如何对齐 wrfout CCTM MCIP 这三个的时间设置（因为ICON/BCON自动对齐MCIP输出时间、m3tshift只需要对齐年份、daymixtocmaq依赖于MCIP的输出，所以这几个环节基本都自动对齐MCIP，比较符合要求），只有理解清楚了这个时间设置原则，才能正确设置每个环节的时间参数，才能让整个 WRF-daymixtocmaq-CMAQ 模型流程顺利跑通！！！！！！

- 更新于 2026-06-06 21:33:00 
---------------------------------------------------------------------------------------------------------------------------------




**友情链接**:
1. [WPS-WRF网格设计工具](https://jiririchter.github.io/WRFDomainWizard/)
2. [FNL-0.25deg气象资料](https://gdex.ucar.edu/datasets/d083003/)
3. 处理过的MIXv2-2017-CB05数据库 （Windows PC:"D:\HPC_Projects\常用数据库\MIXv2-2017-CB05数据库"）