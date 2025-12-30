"""
报告生成器
生成HTML格式的可交互分析报告
"""
import json
import csv
from datetime import datetime
from pathlib import Path


class ReportGenerator:
    # Chart.js库内容缓存（延迟加载）
    _chartjs_content = None
    
    @classmethod
    def _get_chartjs_content(cls) -> str:
        """获取Chart.js库内容（用于内嵌到HTML中，实现离线使用）"""
        if cls._chartjs_content is None:
            chartjs_path = Path(__file__).parent / "chartjs.min.js"
            if chartjs_path.exists():
                content = chartjs_path.read_text(encoding='utf-8')
                # 保护 Chart.js 中的 }} 和 {{ 不被后续的模板替换影响
                # 使用占位符替换，在最终输出前还原
                content = content.replace('}}', '__CHARTJS_DOUBLE_CLOSE__')
                content = content.replace('{{', '__CHARTJS_DOUBLE_OPEN__')
                cls._chartjs_content = content
            else:
                # 如果本地文件不存在，使用CDN作为备选
                cls._chartjs_content = None
        return cls._chartjs_content
    """HTML报告生成器"""
    
    @staticmethod
    def generate_chart_data(results: list) -> dict:
        """
        生成延时曲线数据
        
        Args:
            results: 分析结果列表
            
        Returns:
            图表数据字典 {'frames': [...], 'delays': [...], 'times': [...]}
        """
        # 过滤掉延时为空的数据和状态为"wrong"的异常数据
        valid_data = [r for r in results if r.get('delay_ms') is not None and r.get('status') != 'wrong']
        if not valid_data:
            return {'frames': [], 'delays': [], 'times': []}
        
        return {
            'frames': [r.get('frame_idx', 0) for r in valid_data],
            'delays': [r.get('delay_ms', 0) for r in valid_data],
            'times': [r.get('video_time_s', 0) for r in valid_data]
        }
    
    @staticmethod
    def generate_statistics(results: list) -> dict:
        """
        生成统计数据
        
        Args:
            results: 分析结果列表
            
        Returns:
            统计数据字典
        """
        # 过滤掉延时为空的数据和状态为"wrong"的异常数据
        valid_data = [r for r in results if r.get('delay_ms') is not None and r.get('status') != 'wrong']
        
        if not valid_data:
            return {
                'avg_delay': 0,
                'min_delay': 0,
                'max_delay': 0,
                'valid_count': 0,
                'total_count': len(results)
            }
        
        return {
            'avg_delay': sum(r.get('delay_ms', 0) for r in valid_data) / len(valid_data),
            'min_delay': min(r.get('delay_ms', 0) for r in valid_data),
            'max_delay': max(r.get('delay_ms', 0) for r in valid_data),
            'valid_count': len(valid_data),
            'total_count': len(results)
        }
    
    @staticmethod
    def load_network_data(network_csv: str) -> dict:
        """
        加载网络数据CSV
        
        Args:
            network_csv: 网络数据CSV文件路径
            
        Returns:
            网络数据字典
        """
        print(f"[DEBUG] 尝试加载网络数据: {network_csv}")
        if not network_csv or not Path(network_csv).exists():
            print(f"[DEBUG] 网络数据文件不存在或路径为空")
            return None
        
        print(f"[DEBUG] 网络数据文件存在，开始读取...")
        data = {
            'timestamps': [],
            'phone_ping': [],
            'pc_ping': [],
            'has_phone': False,
            'has_pc': False
        }
        
        try:
            with open(network_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row_count = 0
                for row in reader:
                    row_count += 1
                    data['timestamps'].append(float(row['timestamp']))
                    
                    # 手机ping
                    if 'phone_ping_ms' in row:
                        data['has_phone'] = True
                        phone_ping = row.get('phone_ping_ms')
                        data['phone_ping'].append(float(phone_ping) if phone_ping and phone_ping != '' else None)
                    
                    # 电脑ping
                    if 'pc_ping_ms' in row:
                        data['has_pc'] = True
                        pc_ping = row.get('pc_ping_ms')
                        data['pc_ping'].append(float(pc_ping) if pc_ping and pc_ping != '' else None)
            
            print(f"[DEBUG] 读取了 {row_count} 行数据，has_phone={data['has_phone']}, has_pc={data['has_pc']}")
            result = data if (data['has_phone'] or data['has_pc']) else None
            print(f"[DEBUG] 返回结果: {'有网络数据' if result else '无网络数据'}")
            return result
        except Exception as e:
            print(f"[ERROR] 加载网络数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @classmethod
    def generate_html(
        cls,
        results: list,
        video_filename: str,
        fps: float,
        frame_step: int,
        output_path: str,
        output_dir: Path = None,
        network_csv: str = None
    ) -> Path:
        """
        生成HTML报告
        
        Args:
            results: 分析结果列表
            video_filename: 标定视频文件名
            fps: 视频FPS
            frame_step: 跳帧步长
            output_path: 输出HTML文件路径
            network_csv: 合并了网络数据的CSV文件路径（可选）
            
        Returns:
            生成的HTML文件路径
        """
        report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_path = Path(output_path)
        
        # 生成统计数据
        stats = cls.generate_statistics(results)
        
        # 生成图表数据
        chart_data = cls.generate_chart_data(results)
        chart_frames_json = json.dumps(chart_data['frames'])
        chart_delays_json = json.dumps(chart_data['delays'])
        chart_times_json = json.dumps(chart_data['times'])
        
        # 加载网络数据
        network_data = cls.load_network_data(network_csv) if network_csv else None
        has_network = network_data is not None
        
        if has_network:
            network_timestamps_json = json.dumps(network_data['timestamps'])
            network_phone_ping_json = json.dumps(network_data['phone_ping'])
            network_pc_ping_json = json.dumps(network_data['pc_ping'])
        else:
            network_timestamps_json = '[]'
            network_phone_ping_json = '[]'
            network_pc_ping_json = '[]'
        
        # 生成帧数据（用于当前帧显示）
        frame_data_json = json.dumps([{
            'frame_idx': r['frame_idx'],
            'video_time_s': r['video_time_s'],
            'app_time_str': r['app_time_str'],
            'real_time_str': r['real_time_str'],
            'delay_ms': r['delay_ms']
        } for r in results])
        
        # 计算标定视频的FPS
        annotated_fps = fps / frame_step if fps > 0 and frame_step > 0 else 25
        
        # 获取有效数据列表
        valid_data = [r for r in results if r['delay_ms'] is not None]
        
        # HTML模板
        html_content = cls._get_html_template(
            report_time=report_time,
            video_filename=video_filename,
            results=results,
            valid_data=valid_data,
            avg_delay=stats['avg_delay'],
            min_delay=stats['min_delay'],
            max_delay=stats['max_delay'],
            has_network=has_network,
            has_phone=network_data['has_phone'] if has_network else False,
            has_pc=network_data['has_pc'] if has_network else False,
            network_data=network_data
        )
        
        # 替换占位符
        html_content = html_content.replace('__CHART_FRAMES__', chart_frames_json)
        html_content = html_content.replace('__CHART_DELAYS__', chart_delays_json)
        html_content = html_content.replace('__CHART_TIMES__', chart_times_json)
        html_content = html_content.replace('__FRAME_DATA__', frame_data_json)
        html_content = html_content.replace('__ANNOTATED_FPS__', str(annotated_fps))
        html_content = html_content.replace('__HAS_NETWORK__', 'true' if has_network else 'false')
        html_content = html_content.replace('__NETWORK_TIMESTAMPS__', network_timestamps_json)
        html_content = html_content.replace('__NETWORK_PHONE_PING__', network_phone_ping_json)
        html_content = html_content.replace('__NETWORK_PC_PING__', network_pc_ping_json)
        html_content = html_content.replace('__NETWORK_TIMESTAMPS__', network_timestamps_json)
        html_content = html_content.replace('__NETWORK_PHONE_PING__', network_phone_ping_json)
        html_content = html_content.replace('__NETWORK_PC_PING__', network_pc_ping_json)
        
        # 修复双大括号（模板代码中的转义）
        html_content = html_content.replace('{{', '{').replace('}}', '}')
        
        # 还原 Chart.js 中被保护的双大括号
        html_content = html_content.replace('__CHARTJS_DOUBLE_CLOSE__', '}}')
        html_content = html_content.replace('__CHARTJS_DOUBLE_OPEN__', '{{')
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    @classmethod
    def _get_html_template(
        cls,
        report_time: str,
        video_filename: str,
        results: list,
        valid_data: list,
        avg_delay: float,
        min_delay: float,
        max_delay: float,
        has_network: bool = False,
        has_phone: bool = False,
        has_pc: bool = False,
        network_data: dict = None
    ) -> str:
        """
        生成完整的HTML模板
        
        Args:
            report_time: 报告生成时间
            video_filename: 标定视频文件名
            results: 完整结果列表
            valid_data: 有效数据列表
            avg_delay: 平均延时
            min_delay: 最小延时
            max_delay: 最大延时
            
        Returns:
            完整的HTML字符串
        """
        # 获取Chart.js内容（内嵌方式，支持离线使用）
        chartjs_content = cls._get_chartjs_content()
        if chartjs_content:
            # 内嵌方式：直接将Chart.js代码嵌入HTML
            chartjs_script = f"<script>{chartjs_content}</script>"
        else:
            # 备选方式：使用CDN（需要网络）
            chartjs_script = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>视频延时分析报告 - {report_time}</title>
    {chartjs_script}
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; overflow: hidden; }}
        
        .main-layout {{ display: flex; height: 100vh; position: relative; }}
        
        /* 左侧视频区域 - 可滚动 */
        .left-panel {{ 
            width: 45%; 
            min-width: 300px;
            max-width: 80%;
            background: #2c3e50; 
            padding: 20px; 
            overflow-y: auto;
            height: 100vh;
            display: flex; 
            flex-direction: column;
            align-items: center;
        }}
        
        /* 可拖动分隔条 */
        .resizer {{
            width: 5px;
            background: #34495e;
            cursor: col-resize;
            position: relative;
            transition: background 0.2s;
        }}
        
        .resizer:hover {{
            background: #3498db;
        }}
        
        .resizer::after {{
            content: '';
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 20px;
            height: 60px;
            background: rgba(52, 152, 219, 0.3);
            border-radius: 10px;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        
        .resizer:hover::after {{
            opacity: 1;
        }}
        .left-panel h1 {{ 
            color: white; 
            margin-bottom: 20px; 
            margin-top: 20px;
            text-align: center;
            font-size: 24px;
        }}
        .video-container {{ 
            width: 100%; 
            max-width: 800px;
            margin-bottom: 20px;
        }}
        video {{ 
            width: 100%; 
            min-height: 300px;
            max-height: 500px;
            height: auto;
            background: #000;
            border: 3px solid #34495e; 
            border-radius: 8px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        .video-tip {{ 
            background: #34495e; 
            color: #ecf0f1;
            padding: 15px; 
            border-radius: 5px; 
            margin-top: 15px;
            text-align: center;
        }}
        .video-info {{
            background: #34495e;
            color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-top: 15px;
        }}
        .video-info h3 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            text-align: center;
            border-bottom: 2px solid #4a5f7f;
            padding-bottom: 10px;
        }}
        .info-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #4a5f7f;
        }}
        .info-item:last-child {{
            border-bottom: none;
        }}
        .info-label {{
            color: #95a5a6;
            font-size: 14px;
        }}
        .info-value {{
            color: #ecf0f1;
            font-weight: bold;
            font-size: 14px;
        }}
        
        /* 右侧内容区域 - 可滚动 */
        .right-panel {{ 
            flex: 1;
            min-width: 300px;
            background: #f8f9fa; 
            overflow-y: auto;
            padding: 0;
        }}
        
        /* 统计卡片区域 */
        .stats-section {{
            background: white;
            padding: 25px;
            border-bottom: 3px solid #e9ecef;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        
        .stats-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 10px;
            color: white;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transition: transform 0.2s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.2);
        }}
        
        .stat-card.primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        
        .stat-card.success {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }}
        
        .stat-card.warning {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}
        
        .stat-card.info {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }}
        
        .stat-card h3 {{
            font-size: 13px;
            font-weight: 500;
            margin-bottom: 10px;
            opacity: 0.9;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .stat-card .value {{
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 5px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        
        .stat-card .unit {{
            font-size: 12px;
            opacity: 0.8;
        }}
        
        .content-section {{
            padding: 30px;
        }}
        
        h2 {{ color: #2c3e50; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
        .section {{ margin: 20px 0; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        th, td {{ padding: 14px; text-align: left; border-bottom: 1px solid #ecf0f1; }}
        th {{ background-color: #3498db; color: white; font-weight: 600; }}
        tbody tr {{ cursor: pointer; transition: background-color 0.2s; }}
        tbody tr:hover {{ background-color: #e8f4f8; }}
        tbody tr.selected {{ background-color: #d4e9f7; }}
        .status-ok {{ color: #27ae60; font-weight: bold; }}
        .status-fail {{ color: #e74c3c; font-weight: bold; }}
        .time-wrong {{ color: #e74c3c; background-color: #ffe6e6; font-weight: bold; }}
        .error-warning {{ color: #e67e22; font-size: 0.9em; font-style: italic; }}
        
        .tip {{ 
            background: #fff9e6; 
            padding: 15px; 
            border-radius: 8px; 
            margin: 15px 0; 
            border-left: 4px solid #f39c12;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        
        canvas {{ max-width: 100%; }}
    </style>
</head>
<body>
    <div class="main-layout">
        <!-- 左侧：视频固定 -->
        <div class="left-panel">
            <h1>视频延时分析报告</h1>
            <p style="color: #ecf0f1; margin-bottom: 15px; font-size: 14px;">{report_time}</p>
            <div class="video-container">
                <video id="mainVideo" controls preload="auto" style="background: #000;">
                    <source src="{video_filename}" type="video/mp4">
                    <source src="{video_filename}" type="video/x-m4v">
                    <p style="color: white;">您的浏览器不支持视频播放，请尝试：</p>
                    <ul style="color: white; text-align: left;">
                        <li>使用Chrome、Edge或Firefox最新版浏览器</li>
                        <li>检查视频文件是否与HTML在同一文件夹</li>
                        <li>尝试用VLC等播放器直接打开视频文件: {video_filename}</li>
                    </ul>
                </video>
                <div id="video-error-msg" style="display:none; background:#ffe6e6; color:#c0392b; padding:10px; margin-top:10px; border-radius:5px;">
                    <strong>⚠ 视频加载失败</strong><br>
                    可能原因：浏览器不支持此视频编码格式<br>
                    <small>建议：用VLC播放器打开 {video_filename}</small>
                </div>
                <div class="video-tip" id="current-frame-display">
                    <div><strong>蓝框:</strong> T_app <span id="current-app" style="color: #5dade2;">(--)</span></div>
                    <div><strong>绿框:</strong> T_real <span id="current-real" style="color: #58d68d;">(--)</span></div>
                    <div><strong>红字:</strong> 延时 <span id="current-delay" style="color: #ec7063;">--</span></div>
                </div>
                <div class="video-info">
                    <h3>视频信息</h3>
                    <div class="info-item">
                        <span class="info-label">总帧数:</span>
                        <span class="info-value">{len(results)} 帧</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">有效帧数:</span>
                        <span class="info-value">{len(valid_data)} 帧</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">分析时长:</span>
                        <span class="info-value">{(results[-1]['video_time_s'] if results else 0):.2f} 秒</span>
                    </div>
                </div>
                <div class="video-info">
                    <h3>统计数据</h3>
                    <div class="info-item">
                        <span class="info-label">平均延时:</span>
                        <span class="info-value">{avg_delay:.2f} ms</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">最小延时:</span>
                        <span class="info-value">{min_delay:.2f} ms</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">最大延时:</span>
                        <span class="info-value">{max_delay:.2f} ms</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">有效比例:</span>
                        <span class="info-value">{len(valid_data)}/{len(results)}</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 可拖动分隔条 -->
        <div class="resizer" id="resizer"></div>
        
        <!-- 右侧：可滚动内容 -->
        <div class="right-panel">
            <div class="content-section" style="padding-top: 30px;">
                <div class="tip">
                    <strong>交互提示：</strong> 鼠标悬停在曲线或表格上，左侧视频会自动定位到对应帧
                </div>
                
                <h2>1. 延时分析</h2>
                <div class="section">
                    <canvas id="delayChart"></canvas>
                </div>
"""
        
        # 网络监控独立图表（可选，如果需要更详细的网络分析）
        section_number = 2
        
        # 表格标题根据是否有网络数据动态调整
        table_headers = """
                            <th>帧号</th>
                            <th>视频时间(s)</th>
                            <th>T_app</th>
                            <th>T_real</th>
                            <th>延时(ms)</th>
                            <th>状态</th>
"""
        if has_network:
            table_headers += """
                            <th>手机Ping</th>
                            <th>📶</th>
                            <th>电脑Ping</th>
                            <th>📶</th>
"""
        table_headers += """
                            <th>异常原因</th>
"""
        
        html_content += f"""
            <h2>{section_number}. 详细数据</h2>
            <div class="section">
                <table>
                    <thead>
                        <tr>
{table_headers}
                        </tr>
                    </thead>
                    <tbody>
"""
        
        # 生成表格行
        for i, r in enumerate(results):
            status_class = "status-ok" if r['status'] == 'ok' else "status-fail"
            video_time = r['video_time_s'] if r['video_time_s'] else 0
            video_time_str = f"{r['video_time_s']:.3f}" if r['video_time_s'] else 'N/A'
            
            # 检查是否有错误标记
            app_time_display = r['app_time_str'] or 'N/A'
            real_time_display = r['real_time_str'] or 'N/A'
            app_time_class = 'time-wrong' if r.get('app_time_wrong', False) else ''
            real_time_class = 'time-wrong' if r.get('real_time_wrong', False) else ''
            
            delay_display = r['delay_ms'] if r['delay_ms'] is not None else 'N/A'
            
            # 获取异常原因
            error_reason = r.get('error_reason', '') or ''
            error_class = "error-warning" if error_reason else ""
            
            # 构建表格行
            row_html = f"""
            <tr onmouseenter="seekVideo({i}, this)" data-time="{video_time}" data-frame-index="{i}">
                <td>{r['frame_idx']}</td>
                <td>{video_time_str}</td>
                <td class="{app_time_class}">{app_time_display}</td>
                <td class="{real_time_class}">{real_time_display}</td>
                <td>{delay_display}</td>
                <td class="{status_class}">{r['status']}</td>
"""
            
            # 如果有网络数据，添加网络列
            if has_network and network_data:
                # 从网络数据中获取对应的ping值
                phone_ping = network_data['phone_ping'][i] if i < len(network_data['phone_ping']) else None
                pc_ping = network_data['pc_ping'][i] if i < len(network_data['pc_ping']) else None
                
                # 手机Ping和状态
                if phone_ping is not None:
                    phone_display = f"{phone_ping:.0f}ms"
                    if phone_ping < 100:
                        phone_status = '<span style="color: #27ae60;">🟢</span>'
                    elif phone_ping < 200:
                        phone_status = '<span style="color: #f39c12;">🟡</span>'
                    else:
                        phone_status = '<span style="color: #e74c3c;">🔴</span>'
                else:
                    phone_display = 'N/A'
                    phone_status = '<span style="color: #e74c3c;">🔴</span>'
                
                # 电脑Ping和状态
                if pc_ping is not None:
                    pc_display = f"{pc_ping:.0f}ms"
                    if pc_ping < 100:
                        pc_status = '<span style="color: #27ae60;">🟢</span>'
                    elif pc_ping < 200:
                        pc_status = '<span style="color: #f39c12;">🟡</span>'
                    else:
                        pc_status = '<span style="color: #e74c3c;">🔴</span>'
                else:
                    pc_display = 'N/A'
                    pc_status = '<span style="color: #e74c3c;">🔴</span>'
                
                row_html += f"""
                <td style="font-family: Consolas, monospace;">{phone_display}</td>
                <td>{phone_status}</td>
                <td style="font-family: Consolas, monospace;">{pc_display}</td>
                <td>{pc_status}</td>
"""
            
            row_html += f"""
                <td class="{error_class}">{error_reason if error_reason else '-'}</td>
            </tr>
"""
            html_content += row_html
        
        html_content += """
                    </tbody>
                </table>
            </div>
            </div><!-- end content-section -->
        </div><!-- end right-panel -->
    </div><!-- end main-layout -->
    
    <script>
        // 监听视频加载错误
        const videoElement = document.getElementById('mainVideo');
        const errorMsgElement = document.getElementById('video-error-msg');
        
        if (videoElement && errorMsgElement) {{
            videoElement.addEventListener('error', function(e) {{
                console.error('视频加载错误:', e);
                errorMsgElement.style.display = 'block';
            }}, true);
            
            videoElement.addEventListener('loadeddata', function() {{
                console.log('视频加载成功');
                errorMsgElement.style.display = 'none';
            }});
        }}
        
        // ========== 可拖动分隔条功能 ==========
        const leftPanel = document.querySelector('.left-panel');
        const rightPanel = document.querySelector('.right-panel');
        const resizer = document.getElementById('resizer');
        
        let isResizing = false;
        
        // 从localStorage加载上次的宽度比例
        const savedWidth = localStorage.getItem('leftPanelWidth');
        if (savedWidth) {{
            leftPanel.style.width = savedWidth;
        }}
        
        resizer.addEventListener('mousedown', (e) => {{
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        }});
        
        document.addEventListener('mousemove', (e) => {{
            if (!isResizing) return;
            
            const containerWidth = document.querySelector('.main-layout').offsetWidth;
            const newLeftWidth = (e.clientX / containerWidth) * 100;
            
            // 限制宽度范围: 20% - 80%
            if (newLeftWidth >= 20 && newLeftWidth <= 80) {{
                leftPanel.style.width = newLeftWidth + '%';
            }}
        }});
        
        document.addEventListener('mouseup', () => {{
            if (isResizing) {{
                isResizing = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                
                // 保存当前宽度到localStorage
                localStorage.setItem('leftPanelWidth', leftPanel.style.width);
                console.log('[保存布局] 左侧宽度:', leftPanel.style.width);
            }}
        }});
        
        // ========== 视频和数据显示功能 ==========
        const video = document.getElementById('mainVideo');
        let currentRow = null;
        let pendingSeekData = null;
        
        // 视频错误处理
        video.addEventListener('error', (e) => {{
            console.error('[视频错误]', e);
            console.error('视频路径:', video.src);
            console.error('错误代码:', video.error ? video.error.code : 'unknown');
        }});
        
        video.addEventListener('loadstart', () => {{
            console.log('[视频开始加载]', video.src);
        }});
        
        video.addEventListener('canplay', () => {{
            console.log('[视频可以播放]');
        }});
        
        function seekVideo(frameIndex, row) {
            pendingSeekData = { frameIndex, row };
            isManualSeeking = true;
            console.log('[seekVideo] frameIndex=', frameIndex, 'delay=', frameData[frameIndex]?.delay_ms);
            const exactTime = (frameIndex + 0.5) / annotatedFPS;
            console.log('[seekVideo] 跳转到帧中点时间=', exactTime.toFixed(4), '秒');
            if (!video.paused) {
                video.pause();
            }
            video.currentTime = exactTime;
        }
        
        function updateDisplayData(frameIndex) {
            if (frameIndex >= 0 && frameIndex < frameData.length) {
                const frame = frameData[frameIndex];
                console.log('[更新显示] 原始帧', frame.frame_idx, '延时', frame.delay_ms + 'ms');
                document.getElementById('current-app').textContent = frame.app_time_str ? '(' + frame.app_time_str + ')' : '(--)';
                document.getElementById('current-real').textContent = frame.real_time_str ? '(' + frame.real_time_str + ')' : '(--)';
                document.getElementById('current-delay').textContent = frame.delay_ms !== null ? frame.delay_ms + 'ms' : '--';
                currentFrameIndex = frameIndex;
            }
        }
        
        const rows = document.querySelectorAll('tbody tr');
        rows.forEach(row => {{
            row.addEventListener('click', function() {{
                const frameIndex = parseInt(this.dataset.frameIndex);
                seekVideo(frameIndex, this);
                video.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }});
        }});
        
        const chartFrames = __CHART_FRAMES__;
        const chartDelays = __CHART_DELAYS__;
        const chartTimes = __CHART_TIMES__;
        const hasNetwork = __HAS_NETWORK__;
        const networkTimestamps = __NETWORK_TIMESTAMPS__;
        const networkPhonePing = __NETWORK_PHONE_PING__;
        const networkPcPing = __NETWORK_PC_PING__;
        
        if (chartFrames.length > 0) {{
            const ctx = document.getElementById('delayChart').getContext('2d');
            
            // 准备数据集
            const datasets = [];
            
            // 第1层：电脑Ping（背景阴影 - 淡蓝色）
            if (hasNetwork && networkPcPing.length > 0) {{
                datasets.push({{
                    label: '电脑Ping (ms)',
                    data: networkPcPing,
                    borderColor: 'rgba(52, 152, 219, 0.4)',
                    backgroundColor: 'rgba(52, 152, 219, 0.15)',
                    borderWidth: 1,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1',
                    order: 3
                }});
            }}
            
            // 第2层：手机Ping（背景阴影 - 淡红色）
            if (hasNetwork && networkPhonePing.length > 0) {{
                datasets.push({{
                    label: '手机Ping (ms)',
                    data: networkPhonePing,
                    borderColor: 'rgba(231, 76, 60, 0.4)',
                    backgroundColor: 'rgba(231, 76, 60, 0.15)',
                    borderWidth: 1,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y1',
                    order: 2
                }});
            }}
            
            // 第3层：视频延时（主角 - 粗绿线）
            datasets.push({{
                label: '视频延时 (ms)',
                data: chartDelays,
                borderColor: '#27ae60',
                backgroundColor: 'transparent',
                borderWidth: 3,
                pointRadius: 0,
                pointHoverRadius: 7,
                pointHoverBackgroundColor: '#27ae60',
                pointHoverBorderColor: 'white',
                pointHoverBorderWidth: 2,
                tension: 0.4,
                fill: false,
                yAxisID: 'y',
                order: 1
            }});
            
            const chartConfig = {{
                type: 'line',
                data: {{
                    labels: chartFrames,
                    datasets: datasets
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: true,
                    interaction: {{
                        mode: 'index',
                        intersect: false
                    }},
                    plugins: {{
                        legend: {{
                            display: true,
                            position: 'top'
                        }},
                        tooltip: {{
                            backgroundColor: 'rgba(0, 0, 0, 0.8)',
                            padding: 12,
                            titleFont: {{ size: 13, weight: 'bold' }},
                            bodyFont: {{ size: 12 }},
                            bodySpacing: 6
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: '帧号',
                                font: {{ size: 13, weight: 'bold' }}
                            }}
                        }},
                        y: {{
                            type: 'linear',
                            position: 'left',
                            title: {{
                                display: true,
                                text: '📊 延时 (ms)',
                                color: '#27ae60',
                                font: {{ size: 14, weight: 'bold' }}
                            }},
                            ticks: {{
                                color: '#27ae60',
                                font: {{ size: 12, weight: '600' }}
                            }},
                            grid: {{
                                color: 'rgba(39, 174, 96, 0.1)',
                                lineWidth: 1
                            }}
                        }}
                    }},
                    onHover: function(event, activeElements) {{
                        if (activeElements.length > 0) {{
                            const idx = activeElements[0].index;
                            seekVideo(idx, null);
                        }}
                    }},
                    onClick: function(event, activeElements) {{
                        if (activeElements.length > 0) {{
                            const idx = activeElements[0].index;
                            seekVideo(idx, null);
                            video.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}
                    }}
                }}
            }};
            
            // 如果有网络数据，添加右Y轴
            if (hasNetwork && (networkPhonePing.length > 0 || networkPcPing.length > 0)) {{
                chartConfig.options.scales.y1 = {{
                    type: 'linear',
                    position: 'right',
                    title: {{
                        display: true,
                        text: '📶 Ping延迟 (ms)',
                        color: '#95a5a6',
                        font: {{ size: 14, weight: 'bold' }}
                    }},
                    ticks: {{
                        color: '#95a5a6',
                        font: {{ size: 12 }}
                    }},
                    grid: {{
                        drawOnChartArea: false,
                        color: 'rgba(149, 165, 166, 0.1)'
                    }}
                }};
            }}
            
            const delayChart = new Chart(ctx, chartConfig);
        }}
"""
        
        html_content += """
        const frameData = __FRAME_DATA__;
        let currentFrameIndex = 0;
        const annotatedFPS = __ANNOTATED_FPS__;
        let isManualSeeking = false;
        
        function updateFrameDisplay() {{
            if (isManualSeeking) {{
                return;
            }}
            const currentTime = video.currentTime;
            let closestFrame = frameData[0];
            let minDiff = Infinity;
            frameData.forEach((frame, index) => {{
                const frameTime = frame.video_time_s !== null && frame.video_time_s !== undefined ? frame.video_time_s : 0;
                const diff = Math.abs(currentTime - frameTime);
                if (diff < minDiff) {{
                    minDiff = diff;
                    closestFrame = frame;
                    currentFrameIndex = index;
                }}
            }});
            document.getElementById('current-app').textContent = closestFrame.app_time_str ? '(' + closestFrame.app_time_str + ')' : '(--)';
            document.getElementById('current-real').textContent = closestFrame.real_time_str ? '(' + closestFrame.real_time_str + ')' : '(--)';
            document.getElementById('current-delay').textContent = closestFrame.delay_ms !== null ? closestFrame.delay_ms + 'ms' : '--';
        }}
        
        video.addEventListener('timeupdate', updateFrameDisplay);
        video.addEventListener('loadeddata', () => {{
            // 视频加载完成后，立即显示第一帧数据
            if (frameData.length > 0) {{
                const firstFrame = frameData[0];
                document.getElementById('current-app').textContent = firstFrame.app_time_str ? '(' + firstFrame.app_time_str + ')' : '(--)';
                document.getElementById('current-real').textContent = firstFrame.real_time_str ? '(' + firstFrame.real_time_str + ')' : '(--)';
                document.getElementById('current-delay').textContent = firstFrame.delay_ms !== null ? firstFrame.delay_ms + 'ms' : '--';
            }}
        }});
        
        // 页面加载完成后也立即显示第一帧数据
        window.addEventListener('load', () => {{
            if (frameData.length > 0) {{
                const firstFrame = frameData[0];
                document.getElementById('current-app').textContent = firstFrame.app_time_str ? '(' + firstFrame.app_time_str + ')' : '(--)';
                document.getElementById('current-real').textContent = firstFrame.real_time_str ? '(' + firstFrame.real_time_str + ')' : '(--)';
                document.getElementById('current-delay').textContent = firstFrame.delay_ms !== null ? firstFrame.delay_ms + 'ms' : '--';
            }}
        }});
        
        video.addEventListener('seeked', () => {{
            console.log('[seeked] video.currentTime=', video.currentTime.toFixed(4));
            if (pendingSeekData) {{
                const {{ frameIndex, row }} = pendingSeekData;
                console.log('[seeked] 将在200ms后更新显示: frameIndex=', frameIndex, 'delay=', frameData[frameIndex]?.delay_ms);
                setTimeout(() => {{
                    console.log('[延迟更新] 现在更新显示: frameIndex=', frameIndex);
                    updateDisplayData(frameIndex);
                    if (row) {{
                        if (currentRow) {{
                            currentRow.classList.remove('selected');
                        }}
                        currentRow = row;
                        currentRow.classList.add('selected');
                    }}
                    pendingSeekData = null;
                    isManualSeeking = false;
                    console.log('[完成] isManualSeeking = false');
                }}, 200);
            }} else {{
                setTimeout(() => {{
                    isManualSeeking = false;
                    console.log('[清除标志] isManualSeeking = false');
                }}, 100);
            }}
        }});
    </script>
</body>
</html>
"""
        return html_content

