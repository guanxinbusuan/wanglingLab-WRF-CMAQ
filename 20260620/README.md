# WRF-CMAQ 20260620 实验
- 操作于 20260620 —— 20260625


## 实验内容
在刘老师的不嵌套模拟的CMAQ的操作流基础上，拓展出自己的嵌套工作流，利用  WRF-CMAQ 20260502 实验的实验结果 （不嵌套的 d01 的 CCTM和 MCIP 输出），进行嵌套(d02域)的CCTM模拟试验；



## 实验目的
1. 利用  WRF-CMAQ 20260502 实验的实验结果 （不嵌套的 d01 的 CCTM和 MCIP 输出），进行嵌套(d02域)的CCTM模拟试验；
2. 确认自己设计出的 CMAQ 操作流是否可用于嵌套，如若确认成功，整个模型链即可投入正式论文实验的生产环境




## 实验流程--WRF部分
> 因为WRF体系的数值模式都是two-way-nesting设计思路，其d01/d02/d03的模拟结果都是一锅出，只是因为CMAQ是one-way-nesting设计思路,从MCIP步骤开始都是逐个嵌套域的单独操作，所以两个嵌套域即可通过ICON/BCON将输出结果链接进行嵌套式spin-up

此步骤和 WRF-CMAQ 20260502 实验的 WRF部分实验流程一模一样，且因为WRF体系的数值模式都是two-way-nesting设计，所以和WRF-CMAQ 20260502 实验共用完全同样的 WRF 模拟设置、实验操作流和输出结果文件。







## 实验流程--CMAQ部分
### MCIP使用流程

- MCIP需要根据每个嵌套区域单独操作，WRF-CMAQ 20260502 实验只操作了d01嵌套域，所以本次 WRF-CMAQ 20260620 实验需要操作 d02 嵌套域
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
./run_mcip_d02.csh >&! mcip_d02.log
```
PS：在我的超算环境中，我已通过env.sh脚本硬编码了两个关键环境变量
```bash
export CMAQ_HOME=/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/app
export CMAQ_DATA=/work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/case/data
```

- 记得把 MCIP 的11个输出文件中 `GRIDCRO2D_202409.nc、LUFRAC_CRO_202409.nc、METCRO3D_202409.nc` 这3个nc文件拷贝到 Windows本地，放在工程目录下的 `mcip/mcip-out/${domains}/` 的相应目录，方便分离式的本地操作生成真正可输入 CMAQ 的排放清单文件；

- 注意放在相应的domains目录下，别放错了!





### MIX_to_CMAQ操作流程
> 转换脚本 `daymixtocmaq.py` 使用命令：
- 记得指定 domain 和 format 参数(domian根据mcip的输出定(最好每个嵌套域分离式操作)，format推荐统一用nc3)

```cmd
python daymixtocmaq.py d01 --format nc3
python daymixtocmaq.py d02 --format nc3
python daymixtocmaq.py d03 --format nc3
```
PS:我的CMAQ执行流是做了分离式设计，所以这个操作是在Windows本地笔记本完成的




### wrfbiochemi_to_cmaq操作流程
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

2. 然后在Windows本地笔记本运行转换脚本生成运行CMAQ必须的B3GRD文件
> 转换脚本 `wrfbiochemi_to_b3grd.py` 使用命令：
- 记得指定 domain (根据mcip的输出定(最好每个嵌套域分离式操作)) 参数和  <夏季月>  <冬季月> 参数(推荐统一用 7 和 1)
```cmd
python wrfbiochemi_to_b3grd.py d01 7 1 
python wrfbiochemi_to_b3grd.py d02 7 1 
python wrfbiochemi_to_b3grd.py d03 7 1 
```
PS:我的CMAQ执行流是做了分离式设计，所以这个操作是在超算环境和Windows本地笔记本环境所共同完成的








### ICON-BCON操作流程
用d01嵌套域的CCTM输出文件（对应icon/bcon的regrid模式启动）制作d02的IC/BC场文件;

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
./run_icon_d02.csh >&! icon_d02.log
```



#### bcon操作流程
BCON程序也是不覆写的（程序源代码写定的就是尾行加入模式，而非覆写模式），原来目的就是在这里等着呢！
>参考 WRF-CMAQ 20260502 第二个实验日志，第三点

- **反复运行bcon才能让d01的CCTM输出文件完整覆盖d02模拟时间，也才能制作完整模拟时间的BC场文件**


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
./run_bcon_d02.csh >&! bcon_d02.log
```
PS:
1. 反复运行bcon的csh脚本，但每次只需要修改csh脚本中的 DATE 变量（会自动匹配到相应文件，就能完整覆盖完整模拟时间）,本次实验是将`set DATE = "2024-09-05"` 每次反复运行操作都是加一天，直到完成运行`set DATE = "2024-09-08"`
2. icon可以不取消SDATE和STIME的注释，但是bcon的SDATE、STIME、RUNLEN的注释必须都取消，但反复运行时无需修改此三变量






### CCTM操作流程

按照上述步骤生成d02嵌套域的输入IC/BC场文件，人为/生物排放清单文件后:
- 根据相应的路径和名称对run_cctm.csh执行脚本中的d01相关文件和信息进行修改，包括`APPL,NPCOL/NPROW,GRID_NAME`等关键环境变量以及文件名(IC/BC场文件 + 人为/生物排放场nc文件)等，但是，一定不能破坏核心的CCTM的日循环模拟逻辑！

***总结workflow如下:*** 提交到超算集群的计算节点并行执行积分任务，CCTM是多节点多MPI并行程序
```bash
# 根据需求调整好 run_cctm.csh 这个核心脚本的设置 
#请务必理解清楚了 run_cctm.csh 的 CCTM 的逐日模拟循环逻辑
cd $CMAQ_HOME/CCTM/scripts
vim run_cctm_d02.csh

#回到 slurm 脚本目录进行提交
cd $CMAQ_DATA/..
sbatch cmaq_d02.slurm
```





















## 实验日志
记录于 2026-05-29 07:25:00  

> 参考 WRF-CMAQ 20260502 第二个实验日志，第三点

<u>3. 重新运行ICON/BCON 必须删除原来的 ICON/BCON 的输出文件    !!!!! 
他喵的这两个程序无法覆写 (应该是源代码设置的尾行加入模式，而非覆写模式)，会导致CCTM模拟的IC/BC错位！</u>


> 好吧，我现在理解为什么作者在设计CMAQ时，这个ICON/BCON程序不是覆写模式的了


因为只有ICON/BCON是追加模式才能避免覆盖上一轮生成的IC/BC场文件，尤其是BCON这种需要反复操作才能覆盖模拟时间域的程序，只有追加模式的源码写法才能保证BC文件时间正确。

- 更新于 2026-06-25 03:25:00






## 实验日志
记录于 2026-06-21 07:15:00  

关于CMAQ的CCTM的MPI并行的网格分解方案，这里给个AI-Chat的prompt提示词：
```Prompt
    CMAQ 要求二维域分解必须整除网格吗？有余数不可以吗？
    NX = 235
    NY = 205
    如果我有189个核可调度呢，不一定要使用全部核数,请给出最优分配核数的方案（NPCOL X NPROW） 
```

- 更新于 2026-06-21 07:21:00  