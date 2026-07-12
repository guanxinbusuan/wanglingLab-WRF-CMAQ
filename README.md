# WRF-CMAQ 数值模拟实验思路流程框架
Author: 王令
Agent-cli: Reasonix v1.17.10



## 第一个Demo实验与验证
- **UTC20240905---UTC20240908 台风摩羯 WRF-CMAQ 三层嵌套空气质量模拟**

### WRF-CMAQ 20260502 实验
1. 从CMAS北半球季节性文件嵌套热启动d01的CCTM模拟

### WRF-CMAQ 20260620 实验
2. 从d01输出嵌套热启动d02模拟

### WRF-CMAQ 20260630 实验
3. 从d02输出嵌套热启动d03模拟
    3.1. 更新人为/植物源排放清单文件的制作逻辑与算法 `daymixtocmaq` 的 v3 版本 + `wrfbiochemi_to_b3grd` 的 v2 版本


## 流程设计图

![WRF-CMAQ 实验流程设计图](image/wrf_cmaq_flow.png)




- TODO:

    1. 尝试开启海盐排放，OK,这个尝试宣告宣告破产:
        - 其一是开启海洋排放需要额外的OCEAN文件，这个文件需要 `SMOKE+SA` 工具,这会严重破坏我设计的思路流程框架；
        
        - 其二是 `CMAQ V5.3` 的默认/推荐机制 `CB6R3_AE7_AQ` （也是我编译的机制）虽然在海盐气溶胶排放计算方面和专有海洋化学机制 `CB6R3M`或复杂化学机制`SPARC99`差不多，但是对 Br/I/Cl/DMS 等海洋专有化学的模拟机制很简略。
        
        - 所以就**没有必要**折腾这个了，除非海洋相关课题需要，再重新编译`CB6R3M_AE7_AQ`这种海洋专有机制(`SPARC99` 也有稍微复杂一点点的海洋化学),不过这种编译操作都会覆盖掉现有编译的默认机制，这点和wrfchem的chem_opt选择差别非常大。  
        
        - 参考链接：
         [关于海洋化学排放和模拟的OCEAN文件与专有机制](https://github.com/USEPA/CMAQ/blob/main/DOCS/Users_Guide/Tutorials/CMAQ_UG_tutorial_oceanfile.md#option-1-create-ocean-file-from-shapefile-of-domain)
    
    
    
    
    2. 在d03区域尝试开启点源（高架源）排放的相关模拟;OK,这个尝试也基本破产:
       - 除了Pluem-in-Grid 的次网格羽流模拟需要额外高架属性文件以外，普通的默认网格化点源其实就是`daymixtocmaq`的高度轮廓系数分配罢了(用于替代SMOKE的Elevpoint模块计算)。



- END 





- TODO:


    1. 尝试开启过程分析PA，这个似乎可以尝试(貌似还挺重要的)，**有时间记得折腾一下**!!
        - 参考链接：
         [关于CMAQ的流程分析和预算](https://github.com/USEPA/CMAQ/blob/main/DOCS/Users_Guide/CMAQ_UG_ch09_process_analysis.md)







> Last-Update-Time: 2026-07-12 10:00 