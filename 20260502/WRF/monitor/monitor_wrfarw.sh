#!/bin/bash

# --- 1. 配置参数 ---
SLURM_SCRIPT="wrf_slurm.slurm"  # 你的提交脚本名
LOG_FILE="rsl.error.0000"       # WRF生成的运行日志
MONITOR_LOG="monitor_process.log" # 监测脚本自己的日志文件
CHECK_INTERVAL=60               # 每隔60秒检查一次
TIMEOUT_LIMIT=900              # 25分钟 = 1500秒

# 定义写记录函数：仅重定向到文件
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> $MONITOR_LOG
}

# 初始化：清空旧的监测日志
> $MONITOR_LOG

# --- 2. 提交任务 ---
# 捕获提交输出
SUBMIT_OUTPUT=$(sbatch $SLURM_SCRIPT)
JOB_ID=$(echo $SUBMIT_OUTPUT | awk '{print $NF}')

# 检查是否成功获取 JobID
if [[ $JOB_ID =~ ^[0-9]+$ ]]; then
    log_message "Job $JOB_ID submitted successfully. Monitoring started."
else
    log_message "ERROR: Failed to submit job or parse JobID. Output: $SUBMIT_OUTPUT"
    exit 1
fi

# --- 3. 等待日志文件生成 ---
log_message "Waiting for $LOG_FILE to be created (Job might be in queue)..."
while [ ! -f $LOG_FILE ]; do
    # 如果任务在日志生成前就从队列消失了（比如提交参数错误直接退出了）
    if ! squeue -j $JOB_ID > /dev/null 2>&1; then
        log_message "ERROR: Job $JOB_ID disappeared from queue before log file was created."
        exit 1
    fi
    sleep 30
done
log_message "Log file $LOG_FILE detected. Starting activity checks."

# --- 4. 循环监控 ---
while true; do
    # 1. 检查任务是否仍在运行
    if ! squeue -j $JOB_ID | grep -q $JOB_ID; then
        log_message "Job $JOB_ID is no longer in squeue. Monitoring stopped."
        break
    fi

    # 2. 获取当前时间和日志文件最后更新时间
    CURRENT_TIME=$(date +%s)
    LAST_MOD_TIME=$(stat -c %Y $LOG_FILE)
    DIFF=$((CURRENT_TIME - LAST_MOD_TIME))

    # 3. 判定逻辑
    if [ $DIFF -ge $TIMEOUT_LIMIT ]; then
        log_message "CRITICAL: $LOG_FILE has not updated for $DIFF seconds!"
        log_message "Numerical black hole suspected. Executing: scancel $JOB_ID"
        scancel $JOB_ID
        log_message "Job $JOB_ID has been cancelled. Monitor exiting."
        break
    else
        # 仅记录到日志，屏幕保持干净
        log_message "Status Check: $LOG_FILE updated $DIFF seconds ago. (Limit: $TIMEOUT_LIMIT s). Status: OK."
    fi

    # 4. 等待下一次检查
    sleep $CHECK_INTERVAL
done