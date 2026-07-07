#!/bin/bash
#SBATCH --job-name=wrf-real  # 作业名
#SBATCH --nodes=1                   # 强制单节点（必须！）
#SBATCH --ntasks-per-node=1         # 仅1个MPI任务（geogrid不支持MPI）
#SBATCH --cpus-per-task=12           # 单任务用8核（可根据需求调4/16）
#SBATCH --mem=32G                   # 节点内存16GB（格点大则调32G/64G）
#SBATCH --time=00:30:00             # 超时时间（geogrid通常5-10分钟足够）
#SBATCH --partition=wzhcnormal  # 替换为你的集群分区名
#SBATCH --output=real_%j.out     # 输出日志（%j为作业ID）
#SBATCH --error=real_%j.err      # 错误日志


module purge
source /work/home/wangling02/apprepo/wrf_wps/4.5-intelmpi2017/scripts/env.sh
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}

ulimit -s unlimited
ulimit -l unlimited

./real.exe