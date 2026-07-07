#!/bin/bash
#SBATCH -J wrf #作业名称
#SBATCH -p wzhcnormal #队列名称
#SBATCH -N 3 #节点数量
#SBATCH --ntasks-per-node=63 #每节点核心数
#SBATCH --output=wrf.%j.out
#SBATCH --error=wrf.%j.err

module purge
source /work/home/wangling02/apprepo/wrf_wps/4.5-intelmpi2017/scripts/env.sh
export LD_LIBRARY_PATH=/work/home/wangling02/apprepo/wrf_wps/4.5-intelmpi2017/app/mathlib/lib:$LD_LIBRARY_PATH


export HDF5_USE_FILE_LOCKING=FALSE
ulimit -s unlimited


srun --mpi=pmi2 wrf.exe