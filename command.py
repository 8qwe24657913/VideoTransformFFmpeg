import argparse
import os
from typing import Callable, Optional, Sequence

from transform import FilePath, MethodName, RandomizedTransform, Transform

parser = argparse.ArgumentParser(
    description='Transform input file(s) with ffmpeg')

parser.add_argument('input', type=str, nargs='+',
                    help='input file(s) or folder(s) containing input file(s)')
parser.add_argument('-of', '--output_folder', required=False, type=str,
                    help='output folder, if not set, saves name_transformed.suffix into the input folder')

parser.add_argument('-f', '--function', required=False,
                    type=str, nargs='+', help='transform method(s), ordering decides apply order if mixing is not enabled, available methods: {}'.format(' ,'.join(Transform.methods)))
parser.add_argument('-r', '--randomize', required=False, action='store_true',
                    help='use randomized data instead of default data')

# 1 watermark
watermark = parser.add_argument_group('watermark', 'add watermark')
watermark.add_argument('-wi', '--watermark_image', required=False, type=str,
                       nargs='+', help='watermark image(s) or folder(s) containing watermark image(s)')
watermark.add_argument('-wa', '--watermark_alpha', required=False, type=float,
                       help='alpha of watermark, (0, 1], 0 = totally transparent, 1 = totally not transparent')
watermark.add_argument('-wx', '--watermark_x', required=False,
                       type=str, help='x offset of watermark')
watermark.add_argument('-wy', '--watermark_y', required=False,
                       type=str, help='y offset of watermark')
watermark.add_argument('-ws', '--watermark_scale', required=False,
                       type=float, help='scale of watermark, (0, +inf)')
watermark.add_argument('-wr', '--watermark_rotate', '--watermark_angle', dest='watermark_angle', required=False,
                       type=float, help='rotate angle(clockwise) of watermark, [0, 360) in degrees')

# 2 padding
padding = parser.add_argument_group('padding', 'add black padding')
padding.add_argument('-pt', '--padding_top', required=False,
                     type=str, help='width of padding top')
padding.add_argument('-pr', '--padding_right', required=False,
                     type=str, help='width of padding right')
padding.add_argument('-pb', '--padding_bottom', required=False,
                     type=str, help='width of padding bottom')
padding.add_argument('-pl', '--padding_left', required=False,
                     type=str, help='width of padding left')

# 3 duration
duration = parser.add_argument_group('duration', 'change duration by ratio')
duration.add_argument('-ds', '--duration_start_ratio', required=False,
                      type=float, help='start ratio of duration, (0, 1)')
duration.add_argument('-dr', '--duration_ratio', required=False,
                      type=float, help='ratio of duration, (0, 1)')

# 4 scale
scale = parser.add_argument_group('scale', 'scale by ratio')
scale.add_argument('-sr', '--scale_ratio', required=False,
                   type=float, help='ratio of scale, (0, +inf)')

# 5 mirror
mirror = parser.add_argument_group(
    'mirror', 'mirroring horizontally, no option available')

# 6 rotate
rotate = parser.add_argument_group('rotate', 'rotate the input clockwise')
rotate.add_argument('-ra', '--rotate_angle', required=False, type=float,
                    help='rotate angle(clockwise) of input, [0, 360) in degrees')

# 7 brightness
brightness = parser.add_argument_group('brightness', 'change brightness')
brightness.add_argument('-b', '--brightness', metavar='BRIGHTNESS', dest='brightness_brightness', required=False,
                        type=float, help='brightness value')

# 8 crop
crop = parser.add_argument_group('crop', 'crop the input')
crop.add_argument('-cw', '--crop_width', '--crop_w', dest='crop_w', required=False,
                  type=str, help='width **after** cropping')
crop.add_argument('-ch', '--crop_height', '--crop_h', dest='crop_h', required=False,
                  type=str, help='height **after** cropping')
crop.add_argument('-cx', '--crop_x', required=False,
                  type=str, help='x offset of cropping')
crop.add_argument('-cy', '--crop_y', required=False,
                  type=str, help='y offset of cropping')

# 9 mixed
mixed = parser.add_argument_group(
    'mixed', 'mix the transform method(s) randomly')
mixed.add_argument('-m', '--mixed', required=False, action='store_true',
                   help='enable mixing, that would shuffle all the methods in --function')
mixed.add_argument('-mk', '--mixed_k', required=False, type=int, default=3,
                   help='how many transform method(s) should be applied per input, 3 for default')

args = parser.parse_args()


def resolve_files(input: Sequence[FilePath]) -> Sequence[FilePath]:
    files: Sequence[FilePath] = []
    for file in input:
        assert os.path.exists(file), 'invalid path: {}'.format(file)
        if os.path.isdir(file):
            files += resolve_files(os.listdir(file))
        else:
            files.append(file)
    return files


inputs = resolve_files(args.input)
assert len(inputs) > 0, 'should have at least one input'


def output_original_folder(input: FilePath) -> FilePath:
    return '_transformed'.join(os.path.splitext(input))


def output_static_folder(input: FilePath) -> FilePath:
    return os.path.join(args.output_folder, os.path.basename(input))


assign_output: Callable[[
    FilePath], FilePath] = output_static_folder if args.output_folder else output_original_folder


assert args.function or args.mixed, 'should apply at least 1 transform method'

transform_methods: Sequence[MethodName] = args.function or Transform.methods

cls = RandomizedTransform if args.randomize else Transform

arguments = {}
for method in transform_methods:
    argument = {}
    arguments[method] = argument
    for var_name in getattr(cls, method).__code__.co_varnames:
        if var_name != 'self':
            option_name = '_'.join((method, var_name))
            if hasattr(args, option_name):
                argument[var_name] = getattr(args, option_name)

if 'watermark' in arguments:
    image: Optional[Sequence[FilePath]] = args.watermark_image
    assert image is not None, 'should specify watermark image'
    images = resolve_files(image)
    assert len(images) > 0, 'should supply at least 1 watermark image'
    if args.randomize:
        arguments['watermark']['image'] = images
    else:
        assert len(
            images) == 1, 'should supply only 1 watermark image when randomization is not enabled'
        arguments['watermark']['image'] = images[0]

if args.mixed:
    cls.mixed(inputs, arguments, transform_methods,
              args.mixed_k, assign_output)
else:
    for input in inputs:
        transform = cls(input)
        for method in transform_methods:
            getattr(cls, method)(transform, **arguments['method'])
        transform.run(assign_output(input))
