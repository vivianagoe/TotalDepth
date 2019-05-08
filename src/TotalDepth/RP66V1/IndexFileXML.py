import argparse
import collections
import logging
import os
import sys
import time
import typing

from TotalDepth.RP66V1 import ExceptionTotalDepthRP66V1
from TotalDepth.RP66V1.core import Index, LogPassXML, File
from TotalDepth.util import gnuplot
from TotalDepth.util.DirWalk import dirWalk
from TotalDepth.util.bin_file_type import binary_file_type_from_path

__author__  = 'Paul Ross'
__date__    = '2019-04-10'
__version__ = '0.1.0'
__rights__  = 'Copyright (c) 2019 Paul Ross. All rights reserved.'


logger = logging.getLogger(__file__)


IndexResult = collections.namedtuple('IndexResult', 'size_input, size_index, time, exception, ignored')


FRAME_CHUNK = 1024
FRAME_CHUNK = -1024

def read_a_single_index(xml_path_in: str, archive_root: str) -> IndexResult:
    logger.info(f'Reading XML index: {xml_path_in}')
    try:
        t_start = time.perf_counter()
        with Index.RP66V1IndexXMLRead(xml_path_in, archive_root) as rp66v1_index:
            # TODO: Read all frames is chunks of 1024?
            logical_file: Index.RP66V1IndexXMLLogicalFileRead
            for logical_file in rp66v1_index.logical_files:
                log_pass: LogPassXML.LogPassRP66V1IndexXML
                for log_pass in logical_file.log_passes:
                    frame_object: LogPassXML.FrameArrayRP66V1IndexXML
                    for frame_object in log_pass.frame_objects:
                        num_frames = frame_object.number_of_frames
                        if FRAME_CHUNK < 0 or num_frames < FRAME_CHUNK:
                            frame_object.init_arrays(num_frames)
                            for frame_number, iflr_pos in enumerate(frame_object.rle_lrsh.values()):
                                fld: File.FileLogicalData = rp66v1_index.get_logical_data(iflr_pos)
                                frame_object.read(fld, frame_number)
            result = IndexResult(
                os.path.getsize(rp66v1_index.original_file_path),
                os.path.getsize(xml_path_in),
                time.perf_counter() - t_start,
                False,
                False,
            )
            return result
    except ExceptionTotalDepthRP66V1:
        logger.exception(f'Failed to index with ExceptionTotalDepthRP66V1: {xml_path_in}')
        return IndexResult(os.path.getsize(xml_path_in), 0, 0.0, True, False)
    except Exception:
        logger.exception(f'Failed to index with Exception: {xml_path_in}')
        return IndexResult(os.path.getsize(xml_path_in), 0, 0.0, True, False)
    # logger.info(f'Ignoring file type "{bin_file_type}" at {xml_path_in}')
    # return IndexResult(0, 0, 0.0, False, True)


def read_index_dir_or_file(path_in: str, archive_root: str, recurse: bool) -> typing.Dict[str, IndexResult]:
    logging.info(f'index_dir_or_file(): "{path_in}" to "{archive_root}" recurse: {recurse}')
    ret = {}
    if os.path.isdir(path_in):
        for file_in_out in dirWalk(path_in, theFnMatch='', recursive=recurse, bigFirst=False):
            # print(file_in_out)
            ret[file_in_out.filePathIn] = read_a_single_index(file_in_out.filePathIn, archive_root)
    else:
        ret[path_in] = read_a_single_index(path_in, archive_root)
    return ret


def main() -> int:
    description = """usage: %(prog)s [options] file
Reads a RP66V1 index XML file and all the data."""
    print('Cmd: %s' % ' '.join(sys.argv))
    parser = argparse.ArgumentParser(description=description, epilog=__rights__, prog=sys.argv[0])
    parser.add_argument('path_in', type=str, help='Path to the input.')
    parser.add_argument(
        'archive', type=str,
        help='Path to the root directory of the archive.',
        default='',
        # nargs='?',
    )
    parser.add_argument(
        '-r', '--recurse', action='store_true',
        help='Process files recursively. [default: %(default)s]',
    )
    log_level_help_mapping = ', '.join(
        ['{:d}<->{:s}'.format(level, logging._levelToName[level]) for level in sorted(logging._levelToName.keys())]
    )
    log_level_help = f'Log Level as an integer or symbol. ({log_level_help_mapping}) [default: %(default)s]'
    parser.add_argument(
            "-l", "--log-level",
            default=30,
            help=log_level_help
        )
    parser.add_argument(
        "-v", "--verbose", action='count', default=0,
        help="Increase verbosity, additive [default: %(default)s]",
    )
    gnuplot.add_gnuplot_to_argument_parser(parser)
    args = parser.parse_args()
    print('args:', args)
    # return 0

    # Extract log level
    if args.log_level in logging._nameToLevel:
        log_level = logging._nameToLevel[args.log_level]
    else:
        log_level = int(args.log_level)
    # print('Log level:', log_level)
    # Initialise logging etc.
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        #datefmt='%y-%m-%d % %H:%M:%S',
                        stream=sys.stdout)
    # return 0
    # Your code here
    clk_start = time.perf_counter()
    result: typing.Dict[str, IndexResult] = read_index_dir_or_file(
        args.path_in,
        args.archive,
        args.recurse,
    )
    clk_exec = time.perf_counter() - clk_start
    size_index = size_input = 0
    files_processed = 0
    try:
        for path in sorted(result.keys()):
            idx_result = result[path]
            if idx_result.size_input > 0:
                ms_mb = idx_result.time * 1000 / (idx_result.size_input / 1024 ** 2)
                ratio = idx_result.size_index / idx_result.size_input
                print(
                    f'{idx_result.size_input:16,d} {idx_result.size_index:10,d}'
                    f' {idx_result.time:8.3f} {ratio:8.3%} {ms_mb:8.1f} {str(idx_result.exception):5}'
                    f' "{path}"'
                )
                size_input += result[path].size_input
                size_index += result[path].size_index
                files_processed += 1
        if args.gnuplot:
            plot_gnuplot(result, args.gnuplot)
    except Exception as err:
        logger.exception(str(err))
    print('Execution time = %8.3f (S)' % clk_exec)
    if size_input > 0:
        ms_mb = clk_exec * 1000 / (size_input/ 1024**2)
        ratio = size_index / size_input
    else:
        ms_mb = 0.0
        ratio = 0.0
    print(f'Out of  {len(result):,d} processed {files_processed:,d} files of total size {size_input:,d} input bytes')
    print(f'Wrote {size_index:,d} output bytes, ratio: {ratio:8.3%} at {ms_mb:.1f} ms/Mb')
    print('Bye, bye!')
    return 0


if __name__ == '__main__':
    sys.exit(main())
