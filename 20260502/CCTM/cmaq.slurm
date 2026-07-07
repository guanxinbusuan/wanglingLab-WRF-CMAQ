#!/bin/bash
#SBATCH -J cmaq_d01_202409
#SBATCH -p wzhcnormal
#SBATCH -N 3
#SBATCH -n 170
#SBATCH -t 24:00:00
#SBATCH -o cmaq_%j.out
#SBATCH -e cmaq_%j.err

date
module purge
source /work/home/wangling02/apprepo/cmaq/5.3.2-intelmpi2017/scripts/env.sh
cd $CMAQ_HOME/CCTM/scripts/
./run_cctm.csh