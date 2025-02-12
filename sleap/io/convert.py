"""Command line utility for converting between various dataset formats.

Reads:
* SLEAP dataset in .slp, .h5, .json, or .json.zip file
* SLEAP "analysis" file in .h5 format
* LEAP dataset in .mat file
* DeepLabCut dataset in .yaml or .csv file
* DeepPoseKit dataset in .h5 file
* COCO keypoints dataset in .json file

Writes:
* SLEAP dataset (defaults to .slp if no extension specified)
* SLEAP "analysis" file (.h5)

You don't need to specify the input format; this will be automatically detected.

If you don't specify an output path, then by default we will convert to a .slp
dataset file and save it at `<input path>.slp`.

Analysis HDF5:

If you want to export an "analysis" h5 file, use `--format analysis`. If no
output path is specified, the default is 
`<input path>.<video index>_<video filename>.analysis.h5`.

The analysis HDF5 file has these datasets:

* "track_occupancy"    (shape: tracks * frames)
* "tracks"             (shape: frames * nodes * 2 * tracks)
* "track_names"        (shape: tracks)
* "node_names"         (shape: nodes)
* "edge_names"         (shape: nodes - 1)
* "edge_inds"          (shape: nodes - 1)
* "point_scores"       (shape: frames * nodes * tracks)
* "instance_scores"    (shape: frames * tracks)
* "tracking_scores"    (shape: frames * tracks)

Note: the datasets are stored column-major as expected by MATLAB.
This means that if you're working with the file in Python you may want to
first transpose the datasets so they matche the shapes described above.
"""

import argparse
import os
import re

from pathlib import PurePath

from sleap import Labels, Video


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path", help="Path to input file.")
    parser.add_argument(
        "-o",
        "--output",
        dest="outputs",
        action="append",
        default=[],
        help="Path to output file (optional). The analysis format expects an output "
        "path per video in the project. Otherwise, the default naming convention "
        "`<slp path>.<video index>_<video filename>.analysis.h5` will be used for "
        "every video without a specified output path. Multiple outputs can be "
        "specified, each preceeded by --output.",
    )
    parser.add_argument(
        "--format",
        default="slp",
        help="Output format. Default ('slp') is SLEAP dataset; "
        "'analysis' results in analysis.h5 file; "
        "'analysis.nix' results in an analysis nix file;"
        "'h5' or 'json' results in SLEAP dataset "
        "with specified file format.",
    )
    parser.add_argument(
        "--video", default="", help="Path to video (if needed for conversion)."
    )
    return parser


def default_analysis_filename(
    labels: Labels,
    video: Video,
    output_path: str,
    output_prefix: PurePath,
    format_suffix: str = "h5",
) -> str:
    video_idx = labels.videos.index(video)
    vn = PurePath(video.backend.filename)
    filename = str(
        PurePath(
            output_path,
            f"{output_prefix}.{video_idx:03}_{vn.stem}.analysis.{format_suffix}",
        )
    )
    return filename


def main(args: list = None):
    """Entrypoint for `sleap-convert` CLI for converting .slp to different formats.

    Args:
        args: A list of arguments to be passed into sleap-convert.
    """
    parser = create_parser()
    args = parser.parse_args(args=args)

    video_callback = Labels.make_video_callback([os.path.dirname(args.input_path)])
    try:
        labels: Labels = Labels.load_file(args.input_path, video_search=video_callback)
    except TypeError:
        print("Input file isn't SLEAP dataset so attempting other importers...")
        from sleap.io.format import read

        video_path = args.video if args.video else None

        labels = read(
            args.input_path,
            for_object="labels",
            as_format="*",
            video_search=video_callback,
            video=video_path,
        )
    if "analysis" in args.format:
        vids = []
        if len(args.video) > 0:  # if a video is specified
            for v in labels.videos:  # check if it is among the videos in the project
                if args.video in v.backend.filename:
                    vids.append(v)
                    break
        else:
            vids = labels.videos  # otherwise all videos are converted

        outnames = [path for path in args.outputs]
        if len(outnames) < len(vids):
            # if there are less outnames provided than videos to convert...
            out_suffix = "nix" if "nix" in args.format else "h5"
            fn = args.input_path
            fn = re.sub("(\.json(\.zip)?|\.h5|\.slp)$", "", fn)
            fn = PurePath(fn)

            for video in vids[len(outnames) :]:
                dflt_name = default_analysis_filename(
                    labels=labels,
                    video=video,
                    output_path=str(fn.parent),
                    output_prefix=str(fn.stem),
                    format_suffix=out_suffix,
                )
                outnames.append(dflt_name)

        if "nix" in args.format:
            from sleap.io.format.nix import NixAdaptor

            for video, outname in zip(vids, outnames):
                try:
                    NixAdaptor.write(outname, labels, args.input_path, video)
                except ValueError as e:
                    print(e.args[0])
        else:
            from sleap.info.write_tracking_h5 import main as write_analysis

            for video, output_path in zip(vids, outnames):
                write_analysis(
                    labels,
                    output_path=output_path,
                    labels_path=args.input_path,
                    all_frames=True,
                    video=video,
                )

    elif len(args.outputs) > 0:
        print(f"Output SLEAP dataset: {args.outputs[0]}")
        Labels.save_file(labels, args.outputs[0])

    elif args.format in ("slp", "h5", "json"):
        output_path = f"{args.input_path}.{args.format}"
        print(f"Output SLEAP dataset: {output_path}")
        Labels.save_file(labels, output_path)

    else:
        print("You didn't specify how to convert the file.")
        print(args)


if __name__ == "__main__":
    main()
