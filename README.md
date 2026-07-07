# WRF-CMAQ 数值模拟实验思路流程框架
Author: 王令
Date: 2026-07-07
Agent-cli: Reasonix



## 第一个Demo实验与验证
- **UTC20240905---UTC20240908 台风摩羯 WRF-CMAQ 三层嵌套空气质量模拟**

### WRF-CMAQ 20260502 实验
1. 从CMAS北半球季节性文件嵌套热启动d01的CCTM模拟

### WRF-CMAQ 20260620 实验
2. 从d01输出嵌套热启动d02模拟

### WRF-CMAQ 20260630 实验
3. 从d02输出嵌套热启动d03模拟
3.1 更新人为/植物源排放清单文件的制作逻辑与算法 `daymixtocmaq` 的 v3 版本 + `wrfbiochemi_to_b3grd` 的 v2 版本

> Update-Time: 2026-07-07 09:10 



![WRF-CMAQ 实验流程设计图](image/wrf_cmaq_flow.png)