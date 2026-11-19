# -*- coding: utf-8 -*-
"""character_anim.py — 一张角色静图 → 本地 H3 生成动画 → 透明循环帧 + MP4

全本地，不花订阅费。生成走 ComfyUI 的 MiniMax H3（图生视频），
切帧/抠像/找循环走 sprite-gen。

用法:
  python character_anim.py 角色.png --prompt "原地挥手打招呼" -o 输出目录
  python character_anim.py 角色.png --prompt "行走" --seconds 3 -o out/ --key magenta
  python character_anim.py 角色.png --prompt "呼吸待机" -o out/ --no-greenize   # 背景已是纯绿

产出一份报告 anim_report.json，含每步实测数据与产物路径。
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

COMFY = os.environ.get('COMFYUI_BASE', 'http://127.0.0.1:8188')
SPRITE_GEN = os.environ.get('SPRITE_GEN_BIN', r'D:/AI/sprite-gen/.venv/Scripts/sprite-gen.exe')
TEMPLATE = os.environ.get(
    'H3_I2V_TEMPLATE',
    r'D:/Claude/项目/03 项目开发/软件工具/20260917-MiniMaxH3-本地部署/面板/template_i2v.json')
WEBP_BIN = r'D:/Claude/配置/.claude/tools/bin'
GREEN = (0, 255, 0)


def api(path, data=None, timeout=120):
    req = urllib.request.Request(
        COMFY + path,
        data=json.dumps(data).encode('utf-8') if data else None,
        headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def check_comfy():
    try:
        return api('/system_stats', timeout=5)
    except Exception:
        sys.exit('ComfyUI 未运行。先启动: D:\\AI\\ComfyUI\\一键启动-H3全部.bat（或最小只起 8188）')


def detect_bg(im):
    """四角 24x24 区域求均值，作为背景色（容忍色差与压缩噪声）"""
    w, h = im.size
    sr = sg_ = sb = 0
    n = 0
    for bx, by in ((0, 0), (w - 24, 0), (0, h - 24), (w - 24, h - 24)):
        crop = im.crop((bx, by, bx + 24, by + 24))
        px = crop.load()
        for y in range(24):
            for x in range(24):
                r, g, b = px[x, y]
                sr += r
                sg_ += g
                sb += b
                n += 1
    return (round(sr / n), round(sg_ / n), round(sb / n))


def greenize(src, dst, tol=30):
    """把纯色背景换成纯绿，返回替换比例；背景不纯时报错"""
    from PIL import Image
    im = Image.open(src).convert('RGB')
    bg = detect_bg(im)
    px = im.load()
    w, h = im.size
    n = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - bg[0]) < tol and abs(g - bg[1]) < tol and abs(b - bg[2]) < tol:
                px[x, y] = GREEN
                n += 1
    ratio = n / (w * h)
    if ratio < 0.25:
        sys.exit(f'背景不像纯色（仅 {ratio:.0%} 像素接近角部色 {bg}）。换纯色背景的图，或用 --no-greenize。')
    im.save(dst)
    return bg, ratio


def fit_with_margin(src, dst, fill=0.62):
    """人物缩到画布高度 fill 倍并居中，给动作留出空间，避免视频里出画"""
    import numpy as np
    from PIL import Image
    im = Image.open(src).convert('RGB')
    bg = detect_bg(im)
    a = np.asarray(im).astype(int)
    diff = np.abs(a - np.array(bg))
    mask = (diff >= 30).any(axis=2)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        sys.exit('找不到人物（整张图都是背景色）')
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    person = im.crop((x0, y0, x1 + 1, y1 + 1))
    W, H = im.size
    target_h = int(H * fill)
    scale = target_h / person.height
    if scale < 1:
        person = person.resize((max(1, int(person.width * scale)), target_h), Image.LANCZOS)
    canvas = Image.new('RGB', (W, H), GREEN)
    canvas.paste(person, ((W - person.width) // 2, (H - person.height) // 2))
    canvas.save(dst)
    return {'person_px': [int(x1 - x0 + 1), int(y1 - y0 + 1)],
            'canvas_px': [W, H], 'fill': fill}


def upload(path):
    name = os.path.basename(path)
    b = b'----b'
    body = (b'--' + b + b'\r\nContent-Disposition: form-data; name="image"; filename="'
            + name.encode() + b'"\r\nContent-Type: image/png\r\n\r\n'
            + open(path, 'rb').read() + b'\r\n--' + b + b'\r\nContent-Disposition: form-data; '
            b'name="overwrite"\r\n\r\ntrue\r\n--' + b + b'--\r\n')
    req = urllib.request.Request(
        COMFY + '/upload/image', data=body,
        headers={'Content-Type': 'multipart/form-data; boundary=----b'})
    return json.load(urllib.request.urlopen(req, timeout=120))['name']


def build_workflow(image_name, prompt, seconds, seed):
    wf = json.load(open(TEMPLATE, encoding='utf-8'))
    for node in wf.values():
        inp = node.get('inputs', {})
        ct = node.get('class_type')
        if ct == 'MiniMaxH3ImageToVideo':
            inp['prompt'] = prompt
        elif ct == 'PrimitiveFloat':
            inp['value'] = seconds
        elif ct == 'PrimitiveBoolean':
            inp['value'] = True
        elif ct == 'ResolutionSelector':
            inp['megapixels'] = 0.2
            inp['aspect_ratio'] = '3:4 (Portrait Standard)'
        elif ct == 'RandomNoise':
            inp['noise_seed'] = seed
        elif ct == 'LoadImage':
            inp['image'] = image_name
    return wf


def run_i2v(wf):
    while True:
        q = api('/api/queue')
        if not q.get('queue_running') and not q.get('queue_pending'):
            break
        print('  等待 GPU 空闲…', flush=True)
        time.sleep(5)
    t0 = time.time()
    pid = api('/api/prompt', {'prompt': wf})['prompt_id']
    print(f'  已提交 {pid}', flush=True)
    while True:
        time.sleep(8)
        h = api('/api/history/' + pid)
        if pid not in h:
            continue
        st = h[pid].get('status', {})
        if st.get('status_str') == 'error':
            sys.exit('生成失败: ' + json.dumps(st.get('messages', []), ensure_ascii=False)[:600])
        if st.get('completed'):
            out = None
            for v in h[pid].get('outputs', {}).values():
                for fn in (v.get('images') or []) + (v.get('gifs') or []) + (v.get('videos') or []):
                    out = os.path.join(r'D:/AI/ComfyUI/output', fn.get('subfolder', ''), fn['filename'])
            return out, time.time() - t0
        print(f'  生成中 {time.time()-t0:.0f}s', flush=True)


def sg(args, label):
    env = dict(os.environ)
    env['PATH'] = WEBP_BIN + os.pathsep + env.get('PATH', '')
    r = subprocess.run([SPRITE_GEN] + args, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    if r.returncode != 0:
        tail = (r.stdout or '')[-500:] + (r.stderr or '')[-500:]
        print(f'  [{label}] 退出码 {r.returncode}\n{tail}', flush=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image', help='角色静图（全身，纯色背景最好）')
    ap.add_argument('--prompt', required=True, help='动作描述，中文')
    ap.add_argument('-o', '--out', required=True, help='输出目录')
    ap.add_argument('--seconds', type=float, default=3, help='生成时长，默认 3 秒')
    ap.add_argument('--key', default='green', choices=['green', 'magenta', 'white'], help='抠像色键')
    ap.add_argument('--state', default='idle', help='状态名，写进产物文件名')
    ap.add_argument('--no-greenize', action='store_true', help='图已是纯绿底，跳过换底')
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--fill', type=float, default=0.62, help='人物占画布高度比例，默认 0.62，动作大就调小')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {'source': os.path.abspath(args.image), 'prompt': args.prompt,
              'seconds': args.seconds, 'key': args.key, 'steps': {}}

    print('[0/5] 检查环境', flush=True)
    check_comfy()
    if not os.path.exists(SPRITE_GEN):
        sys.exit(f'找不到 sprite-gen: {SPRITE_GEN}')

    print('[1/5] 处理首帧', flush=True)
    if args.no_greenize:
        first = args.image
        report['steps']['greenize'] = 'skipped'
    else:
        first = str(out / 'first.png')
        bg, ratio = greenize(args.image, first)
        report['steps']['greenize'] = {'bg': list(bg), 'replaced_pct': round(ratio * 100, 1)}
        print(f'  背景 {bg} 换成纯绿，替换 {ratio*100:.1f}% 像素', flush=True)
        fitted = str(out / 'first_fitted.png')
        info = fit_with_margin(first, fitted, fill=args.fill)
        first = fitted
        report['steps']['fit'] = info
        print(f'  人物 {info["person_px"]} 缩到画布 {info["canvas_px"]} 的 {info["fill"]:.0%} 高，'
              f'留出动作空间', flush=True)

    print('[2/5] 上传并生成', flush=True)
    upname = upload(first)
    seed = args.seed or int(time.time()) % 1000000
    wf = build_workflow(upname, args.prompt, args.seconds, seed)
    video, elapsed = run_i2v(wf)
    report['steps']['generate'] = {'video': video, 'elapsed_s': round(elapsed), 'seed': seed}
    print(f'  完成 {elapsed:.0f}s -> {video}', flush=True)

    print('[3/5] 切帧抠像', flush=True)
    vf_dir = out / 'vframes'
    sg(['video-frames', '--clip', video, '--out-dir', str(vf_dir),
        '--key', args.key, '--allow-subject-edge-contact'], 'video-frames')

    print('[4/5] 找循环', flush=True)
    vl_dir = out / 'vloop'
    # sprite-gen 只把 CYCLIC_STATES 里的词当循环态，其余一律要求 one-shot
    CYCLIC = {'idle', 'walk', 'run', 'talk', 'blink', 'breathe'}
    state_loop = args.state if args.state in CYCLIC else 'idle'
    if state_loop != args.state:
        print(f'  {args.state} 不在循环状态词表内，按 idle 处理（动作名仍记在报告里）', flush=True)
    base = ['video-loop', '--frames-dir', str(vf_dir / 'keyed'),
            '--out-dir', str(vl_dir), '--state', state_loop]
    r = sg(base, 'video-loop')
    if r.returncode != 0:
        msg = (r.stdout or '') + (r.stderr or '')
        if 'requires --cycle once' in msg or 'one-shot' in msg:
            print('  该状态被判定为一次性动作，改用 once 模式重试', flush=True)
            r = sg(base + ['--cycle', 'once'], 'video-loop(once)')
            if r.returncode == 0:
                report['steps']['loop'] = 'ok (one-shot)'
        if r.returncode != 0:
            report['steps']['loop'] = 'blocked: 未找到周期'
            print('  循环检测退回。多半是动作幅度太小或不是往复动作。\n'
                  '  一是把提示词写成明确往复的动作（"连续快速结印三次"比"缓慢抬手"好）；\n'
                  '  二是这段就当单向动作，用导出的 MP4 即可。', flush=True)
    else:
        report['steps']['loop'] = 'ok'

    print('[5/5] 导出 MP4', flush=True)
    mp4 = out / f'{args.state}.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-framerate', '24',
                    '-i', str(vf_dir / 'keyed' / 'frame-%04d.png'),
                    '-f', 'lavfi', '-i', 'color=c=0x1e222a:s=384x544:d=4',
                    '-filter_complex', '[1:v][0:v]overlay=shortest=1,format=yuv420p',
                    '-c:v', 'libx264', '-crf', '18', '-movflags', '+faststart', str(mp4)])
    report['steps']['export'] = {'mp4': str(mp4)}
    for f in ('loop.gif', 'loop.webp', 'loop.strip.png', 'loop.loop.report.json'):
        if (vl_dir / f).exists():
            report.setdefault('products', {})[f] = str(vl_dir / f)
    report['products']['mp4'] = str(mp4)

    json.dump(report, open(out / 'anim_report.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n完成。产物:', flush=True)
    for k, v in report['products'].items():
        print(f'  {k}: {v}', flush=True)


if __name__ == '__main__':
    main()
