# VideoTransformFFmpeg

使用 ffmpeg 对视频 / 图像进行变换用于数据增强

支持的变换：

- 添加水印
- 在边缘填充黑边
- 从视频中剪切出一段
- 缩放
- 镜像
- 旋转
- 调整亮度
- 裁剪
- 以上八种的随机组合

## API

```python
from transform import Transform, RandomizedTransform
```

### Transform(input)

描述：构造 transform 对象

参数：

- input: 要进行变换的视频 / 图像路径

###  transform#watermark(image, alpha, x, y, scale, angle)

描述：添加水印

参数：

- image: 水印图片路径
- alpha: 透明度，取值范围 [0, 1]
- x / y: 水印的水平 / 竖直偏移量，指水印左上角到要进行变换的视频 / 图像左上角的偏移量
- scale: 水印的缩放比例
- angle: 水印的顺时针旋转角度，以角度制计算

### transform#padding(top, right, bottom, left)

描述：在边缘填充黑边

参数：

- top / right / bottom / left: 上 / 右 / 下 / 左侧黑边的宽度

### transform#duration(start_ratio, ratio)

描述：从**视频**中截取一段

参数：

- start_ratio: 要截取的段的开始位置占视频时长的比例，取值范围 [0, 1]
- ratio: 要截取的段的长度占视频时长的比例，取值范围 [0, 1]最近

**注意：FFmpeg 定位时会自动定位到最近的关键帧，因此可能不会精确定位**

### transform#scale(ratio)

描述：缩放

参数：

- scale: 缩放比例

### transform#mirror()

描述：水平镜像

参数：无

### transform#rotate(angle)

描述：旋转

参数：

- angle: 顺时针旋转的角度，以角度制计算

### transform#brightness(brightness)

描述：调整亮度

参数：

- brightness: 亮度补正

### transform#crop(w, h, x, y)

描述：裁剪

参数：

- w / h: 裁剪的宽度 / 高度
- x / y: 裁剪窗口左上角距该视频 / 图像左上角的偏移量

### Transform.mixed(inputs, args, methods, k, assign_output)

描述：以上八种进行随机组合

参数：

- inputs: 要变换的视频 / 图像的列表

- args: 以上八个函数的参数，以 watermark 方法为例：

  ```python
  # 固定单组参数：
  {
      'watermark': {
          'image': '1.png',
          'alpha': 0.5,
      }
  }
  
  # 对于单个参数的随机：
  {
      'watermark': {
          'image': ['1.png', '2.png'],
          'alpha': 0.5,
      }
  }
  
  # 对于参数组的随机：
  {
      'watermark': [
          {
              'image': ['1.png', '2.png'],
              'alpha': 0.5,
          }, {
              'image': '3.png',
              'alpha': 0.8,
          }
      ]
  }
  
  # 自定义随机：
  {
      'watermark': lambda: random.choices([
          {
              'image': '1.png',
              'alpha': lambda: random.random() * 0.8 + 0.2,
          }, {
              'image': '2.png',
              'alpha': lambda: random.random() * 0.7 + 0.3,
          }
      ], weights=[2, 3])[0]
  }
  ```

- methods: 要使用的变换列表，默认为全部八种变换

- k: 对每个应用几种变换

- assign_output: 为每个输入文件指定一个输出文件，默认为在原文件名后加 `_transformed` 并保存到原目录

### transform#generate_cmd(output, quiet, y, accurate_seek)

描述：生成执行变换所用的命令

参数：

- output: 输出文件路径

- quiet: 静默模式，对应 ffmpeg 的 -v quiet

- y: 不进行确认，对应 ffmpeg 的 -y

- accurate_seek: 精准时间切割，对应 ffmpeg 的 -accurate_seek -avoid_negative_ts 1，**默认不开启**

返回：执行变换所用的命令

### transform#run(output, **kwargs)

描述：执行变换

参数：

- output: 输出文件路径

- **kwargs: 其它 param 参考 generate_cmd()

返回：CompletedProcess 对象

### RandomizedTransform(input)

描述：`Transform` 的子类，但八种变换中的可选参数不传入时默认采用随机参数



使用例：

```python
Transform(video_path)
	.watermark(
        watermark_image,
        alpha = 0.5,
        scale = 0.5,
    )
    .duration(0.1, 0.9)
    .scale(0.5)
    .rotate(90)
    .run(output_video_path)
```



## Command Line API

usage: command.py [-h] [-of OUTPUT_FOLDER] [-f FUNCTION [FUNCTION ...]] [-r]
                  [-wi WATERMARK_IMAGE [WATERMARK_IMAGE ...]] [-wa WATERMARK_ALPHA] [-wx WATERMARK_X]
                  [-wy WATERMARK_Y] [-ws WATERMARK_SCALE] [-wr WATERMARK_ANGLE] [-pt PADDING_TOP] [-pr PADDING_RIGHT]
                  [-pb PADDING_BOTTOM] [-pl PADDING_LEFT] [-ds DURATION_START_RATIO] [-dr DURATION_RATIO]
                  [-sr SCALE_RATIO] [-ra ROTATE_ANGLE] [-b BRIGHTNESS] [-cw CROP_W] [-ch CROP_H] [-cx CROP_X]
                  [-cy CROP_Y] [-m] [-mk MIXED_K]
                  input [input ...]

Transform input file(s) with ffmpeg

positional arguments:
  input                 input file(s) or folder(s) containing input file(s)

optional arguments:
  -h, --help            show this help message and exit
  -of OUTPUT_FOLDER, --output_folder OUTPUT_FOLDER
                        output folder, if not set, saves name_transformed.suffix into the input folder
  -f FUNCTION [FUNCTION ...], --function FUNCTION [FUNCTION ...]
                        transform method(s), ordering decides apply order if mixing is not enabled, available methods:
                        watermark ,padding ,duration ,scale ,rotate ,brightness ,mirror ,crop
  -r, --randomize       use randomized data instead of default data

watermark:
  add watermark

  -wi WATERMARK_IMAGE [WATERMARK_IMAGE ...], --watermark_image WATERMARK_IMAGE [WATERMARK_IMAGE ...]
                        watermark image(s) or folder(s) containing watermark image(s)
  -wa WATERMARK_ALPHA, --watermark_alpha WATERMARK_ALPHA
                        alpha of watermark, (0, 1], 0 = totally transparent, 1 = totally not transparent
  -wx WATERMARK_X, --watermark_x WATERMARK_X
                        x offset of watermark
  -wy WATERMARK_Y, --watermark_y WATERMARK_Y
                        y offset of watermark
  -ws WATERMARK_SCALE, --watermark_scale WATERMARK_SCALE
                        scale of watermark, (0, +inf)
  -wr WATERMARK_ANGLE, --watermark_rotate WATERMARK_ANGLE, --watermark_angle WATERMARK_ANGLE
                        rotate angle(clockwise) of watermark, [0, 360) in degrees

padding:
  add black padding

  -pt PADDING_TOP, --padding_top PADDING_TOP
                        width of padding top
  -pr PADDING_RIGHT, --padding_right PADDING_RIGHT
                        width of padding right
  -pb PADDING_BOTTOM, --padding_bottom PADDING_BOTTOM
                        width of padding bottom
  -pl PADDING_LEFT, --padding_left PADDING_LEFT
                        width of padding left

duration:
  change duration by ratio

  -ds DURATION_START_RATIO, --duration_start_ratio DURATION_START_RATIO
                        start ratio of duration, (0, 1)
  -dr DURATION_RATIO, --duration_ratio DURATION_RATIO
                        ratio of duration, (0, 1)

scale:
  scale by ratio

  -sr SCALE_RATIO, --scale_ratio SCALE_RATIO
                        ratio of scale, (0, +inf)

mirror:
  mirroring horizontally, no option available

rotate:
  rotate the input clockwise

  -ra ROTATE_ANGLE, --rotate_angle ROTATE_ANGLE
                        rotate angle(clockwise) of input, [0, 360) in degrees

brightness:
  change brightness

  -b BRIGHTNESS, --brightness BRIGHTNESS
                        brightness value

crop:
  crop the input

  -cw CROP_W, --crop_width CROP_W, --crop_w CROP_W
                        width **after** cropping
  -ch CROP_H, --crop_height CROP_H, --crop_h CROP_H
                        height **after** cropping
  -cx CROP_X, --crop_x CROP_X
                        x offset of cropping
  -cy CROP_Y, --crop_y CROP_Y
                        y offset of cropping

mixed:
  mix the transform method(s) randomly

  -m, --mixed           enable mixing, that would shuffle all the methods in --function
  -mk MIXED_K, --mixed_k MIXED_K
                        how many transform method(s) should be applied per input, 3 for default



