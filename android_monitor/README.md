# 追梦网络监控助手 - Android APK

## 项目说明
用于在手机端实时监控网络状况，配合视频延时分析工具使用。

## 功能特性
- ✅ 后台持续ping监控
- ✅ 记录延迟、丢包率
- ✅ 导出CSV格式日志
- ✅ 前台通知显示状态
- ✅ 本地文件存储

## 技术栈
- Kotlin
- Android SDK 24+ (Android 7.0+)
- Foreground Service
- File I/O

## 开发环境
- Android Studio Hedgehog | 2023.1.1+
- Gradle 8.0+
- Kotlin 1.9+

## 构建步骤
1. 用Android Studio打开此项目
2. 等待Gradle同步完成
3. 连接手机或启动模拟器
4. 点击Run运行

## 使用方法
1. 输入目标服务器地址
2. 点击"开始监控"
3. 手机会显示前台通知
4. 录制视频测试
5. 点击"停止监控"
6. 点击"导出日志"，通过微信/邮件发送到电脑

## 日志位置
`/sdcard/Documents/NetworkMonitor/network_log_YYYYMMDD_HHMMSS.csv`

## CSV格式
```csv
timestamp,datetime,target,ping_ms,status
1702652400.123,2023-12-15 16:00:00.123,cloud.dreame.tech,45.2,ok
1702652401.234,2023-12-15 16:00:01.234,cloud.dreame.tech,48.5,ok
```

## 权限说明
- INTERNET: 网络访问
- FOREGROUND_SERVICE: 后台服务
- POST_NOTIFICATIONS: 显示通知（Android 13+）
- WRITE_EXTERNAL_STORAGE: 保存日志文件

## 目录结构
```
android_monitor/
├── app/
│   ├── src/
│   │   └── main/
│   │       ├── java/com/dreame/networkmonitor/
│   │       │   ├── MainActivity.kt
│   │       │   ├── NetworkMonitorService.kt
│   │       │   ├── PingUtil.kt
│   │       │   └── CsvLogger.kt
│   │       ├── res/
│   │       │   ├── layout/
│   │       │   │   └── activity_main.xml
│   │       │   ├── values/
│   │       │   │   ├── strings.xml
│   │       │   │   └── colors.xml
│   │       │   └── drawable/
│   │       └── AndroidManifest.xml
│   └── build.gradle.kts
├── gradle/
└── settings.gradle.kts
```


