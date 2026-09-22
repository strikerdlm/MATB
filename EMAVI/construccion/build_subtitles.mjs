import fs from 'node:fs';
import path from 'node:path';

export function buildSubtitles(base, chapters) {
  const stamp = t => {
    const ms = Math.round(t * 1000);
    return `${String(Math.floor(ms / 3600000)).padStart(2, '0')}:${String(Math.floor(ms / 60000) % 60).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
  };
  const cues = [];
  for (const chapter of chapters) {
    const timings = JSON.parse(fs.readFileSync(path.join(base, 'audio', chapter.id + '.timing.json'), 'utf8').replace(/^\uFEFF/, ''));
    if (!timings.every(t => Number.isFinite(t.end_ms))) throw Error('Sentence audio boundaries required: ' + chapter.id);
    for (const sentence of timings) {
      const start = chapter.start + .35 + sentence.start_ms / 1000;
      const end = chapter.start + .35 + sentence.end_ms / 1000;
      if (end <= start || end > chapter.end) throw Error('Invalid subtitle boundary');
      cues.push({start, end, text: sentence.text});
    }
  }
  for (let i = 1; i < cues.length; i++) if (cues[i].start < cues[i - 1].end) throw Error('Overlapping subtitles');
  fs.writeFileSync(path.join(base, 'subtitulos.vtt'), 'WEBVTT\n\n' + cues.map(c => `${stamp(c.start)} --> ${stamp(c.end)}\n${c.text}\n`).join('\n'));
  fs.writeFileSync(path.join(base, 'subtitulos.srt'), cues.map((c, i) => `${i + 1}\n${stamp(c.start).replace('.', ',')} --> ${stamp(c.end).replace('.', ',')}\n${c.text}\n`).join('\n'));
  return {cues: cues.length, nonOverlapping: true, lastEnd: cues.at(-1).end, chapterEnd: chapters.at(-1).end, timingMethod: 'Measured boundaries of individual OpenAI TTS HD sentence WAVs; 350 ms montage offset'};
}
