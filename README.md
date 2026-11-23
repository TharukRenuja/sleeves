# Sleeves

An animated wall of today's top album covers, that updates itself every day...

## Use it

```html
<video poster="https://tharukrenuja.github.io/sleeves/wall.jpg" autoplay muted loop playsinline>
  <source src="https://tharukrenuja.github.io/sleeves/720p/wall.webm" type='video/webm; codecs="av01.0.05M.08"'>
  <source src="https://tharukrenuja.github.io/sleeves/720p/vp9/wall.webm" type="video/webm">
</video>
```

Change `720p` to `360p`, `480p` or `1080p` for a different quality. The list of albums is at `/covers.json`.

## Credits

Album data from [Apple Music charts](https://rss.applemarketingtools.com/). Artwork belongs to its respective owners. Made with [FFmpeg](https://ffmpeg.org), [SVT-AV1](https://gitlab.com/AOMediaCodec/SVT-AV1), [Pillow](https://pillow.readthedocs.io) and [NumPy](https://numpy.org).