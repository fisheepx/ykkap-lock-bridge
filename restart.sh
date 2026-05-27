#!/bin/bash

# 设置日志文件路径
LOG_DIR="/volume1/docker/door-bridge/logs"
LOG_FILE="$LOG_DIR/restart_$(date +%Y%m).log"

# 基本信息记录
echo "----------------------------------------" >> "$LOG_FILE"
echo "$(date) - Starting container restart" >> "$LOG_FILE"

# 切换到工作目录
cd /volume1/docker/door-bridge

# 执行重启
echo "Restarting container..." >> "$LOG_FILE"
docker-compose restart doorlock-control >> "$LOG_FILE" 2>&1
RESTART_RESULT=$?

# 等待服务启动
sleep 30

# 检查容器状态
CONTAINER_STATUS=$(docker ps | grep doorlock-control)
if [ $RESTART_RESULT -eq 0 ] && [ ! -z "$CONTAINER_STATUS" ]; then
    echo "$(date) - Container restart successful" >> "$LOG_FILE"
    echo "$CONTAINER_STATUS" >> "$LOG_FILE"
else
    echo "$(date) - Container restart failed" >> "$LOG_FILE"
fi