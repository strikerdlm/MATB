"""Extract chapter review frames and verify the rebuilt delivery locally."""
from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[1]
chapters = json.loads((BASE / 'video/chapters.json').read_text(encoding='utf-8'))
temporary = BASE / 'construccion/runtime/hd-review'
temporary.mkdir(parents=True, exist_ok=True)
video = BASE / 'entregables/EMAVI_recorrido_es.mp4'
sheet = Image.new('RGB', (1440, 6 * 310), '#07111f')
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 17)
for i, chapter in enumerate(chapters):
    frame = temporary / f'{i:02d}.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(chapter['start'] + chapter['duration'] * .4),
                    '-i', str(video), '-frames:v', '1', '-vf', 'scale=480:270', str(frame)], check=True)
    x, y = (i % 3) * 480, (i // 3) * 310
    with Image.open(frame) as image:
        sheet.paste(image, (x, y))
    ImageDraw.Draw(sheet).text((x + 8, y + 276), f'{i+1:02d}  {chapter["title"]}', font=font, fill='#e6bb69')
sheet.save(BASE / 'revision/storyboard-video.png')
for chapter_id, name in [('pvt', 'video-pvt.png'), ('cognitiva', 'video-cognitiva.png')]:
    chapter = next(c for c in chapters if c['id'] == chapter_id)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(chapter['start'] + chapter['duration'] * .4),
                    '-i', str(video), '-frames:v', '1', str(BASE / 'revision' / name)], check=True)
print('18 chapter frames and two full-resolution review frames refreshed.')
