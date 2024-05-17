import os
import uuid
from abc import abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, Sequence


@dataclass
class PathInfo:
    """
    Information about where and how to write a file.

    The bluesky event model splits the URI for a resource into two segments to aid in
    different applications mounting filesystems at different mount points.
    The portion of this path which is relevant only for the writer is the 'root',
    while the path from an agreed upon mutual mounting is the resource_path.
    The resource_dir is used with the filename to construct the resource_path.

    :param root: Path of a root directory, relevant only for the file writer
    :param resource_dir: Directory into which files should be written, relative to root
    :param filename: Base filename to use generated by FilenameProvider, w/o extension
    :param create_dir_depth: Optional depth of dirs to create if they do not exist
    """

    root: Path
    resource_dir: Path
    filename: str
    create_dir_depth: int = 0


class FilenameProvider(Protocol):
    @abstractmethod
    def __call__(self) -> str:
        """Get a filename to use for output data, w/o extension"""


class PathProvider(Protocol):
    _filename_provider: FilenameProvider

    @abstractmethod
    def __call__(self, device_name=None) -> PathInfo:
        """Get the current directory to write files into"""


class StaticFilenameProvider(FilenameProvider):
    def __init__(self, filename: str):
        self._static_filename = filename

    def __call__(self) -> str:
        return self._static_filename


class UUIDFilenameProvider(FilenameProvider):
    def __init__(self, uuid_call_func: callable = uuid.uuid4):
        self._uuid_call_func = uuid_call_func
        self._uuid_namespace = None
        self._uuid_name = None

    def specify_uuid_namespace(self, namespace, name):
        self._uuid_namespace = namespace
        self._uuid_name = name

    def __call__(self) -> str:
        if self._uuid_call_func in [uuid.uuid3, uuid.uuid5]:
            if self._uuid_namespace is None or self._uuid_name is None:
                raise ValueError(
                    f"To use {self._uuid_call_func} to generate UUID filenames,"
                    " UUID namespace and name must be set!"
                )
            uuid_str = self._uuid_call_func(self._uuid_namespace, self._uuid_name)
        else:
            uuid_str = self._uuid_call_func()
        return f"{uuid_str}"


class AutoIncrementFilenameProvider(FilenameProvider):
    def __init__(
        self,
        base_filename: str = "",
        max_digits: int = 5,
        starting_value: int = 0,
        increment: int = 1,
        inc_delimeter: str = "_",
    ):
        self._base_filename = base_filename
        self._max_digits = max_digits
        self._current_value = starting_value
        self._increment = increment
        self._inc_delimeter = inc_delimeter

    def __call__(self):
        if len(str(self._current_value)) > self._max_digits:
            raise ValueError(
                f"Auto incrementing filename counter \
                  exceeded maximum of {self._max_digits} digits!"
            )

        padded_counter = str(self._current_value).rjust(self._max_digits, "0")

        filename = f"{self._base_filename}{self._inc_delimeter}{padded_counter}"

        self._current_value += self._increment
        return filename


class StaticPathProvider(PathProvider):
    def __init__(
        self,
        filename_provider: FilenameProvider,
        directory_path: Path,
        resource_dir: Path = Path("."),
        create_dir_depth: int = 0,
    ) -> None:
        self._filename_provider = filename_provider
        self._directory_path = directory_path
        self._resource_dir = resource_dir
        self._create_dir_depth = create_dir_depth

    def __call__(self, device_name=None) -> PathInfo:
        filename = self._filename_provider()

        return PathInfo(
            root=self._directory_path,
            resource_dir=self._resource_dir,
            filename=filename,
            create_dir_depth=self._create_dir_depth,
        )


class AutoIncrementingPathProvider(PathProvider):
    def __init__(
        self,
        filename_provider: FilenameProvider,
        directory_path: Path,
        create_dir_depth: int = 0,
        max_digits: int = 5,
        starting_value: int = 0,
        num_calls_per_inc: int = 1,
        increment: int = 1,
        inc_delimeter: str = "_",
        base_name: str = None,
    ) -> None:
        self._filename_provider = filename_provider
        self._directory_path = directory_path
        self._create_dir_depth = create_dir_depth
        self._base_name = base_name
        self._starting_value = starting_value
        self._current_value = starting_value
        self._num_calls_per_inc = num_calls_per_inc
        self._inc_counter = 0
        self._max_digits = max_digits
        self._increment = increment
        self._inc_delimeter = inc_delimeter

    def __call__(self, device_name=None) -> PathInfo:
        filename = self._filename_provider()

        padded_counter = str(self._current_value).rjust(self._max_digits, "0")

        resource_dir = str(padded_counter)
        if self._base_name is not None:
            resource_dir = f"{self._base_name}{self._inc_delimeter}{padded_counter}"
        elif device_name is not None:
            resource_dir = f"{device_name}{self._inc_delimeter}{padded_counter}"

        self._inc_counter += 1
        if self._inc_counter == self._num_calls_per_inc:
            self._inc_counter = 0
            self._current_value += 1

        return PathInfo(
            root=self._directory_path,
            resource_dir=resource_dir,
            filename=filename,
            create_dir_depth=self._create_dir_depth,
        )


class YMDPathProvider(PathProvider):
    def __init__(
        self,
        filename_provider: FilenameProvider,
        directory_path: Path,
        create_dir_depth: int = 0,
        device_name_as_base_dir: bool = False,
    ) -> None:
        self._filename_provider = filename_provider
        self._directory_path = directory_path
        self._create_dir_depth = create_dir_depth
        self._device_name_as_base_dir = device_name_as_base_dir

    def __call__(self, device_name=None) -> PathInfo:
        current_date = date.today()
        if device_name is None:
            resource_dir = os.path.join(
                str(current_date.year), str(current_date.month), str(current_date.day)
            )
        elif self._device_name_as_base_dir:
            resource_dir = os.path.join(
                str(current_date.year),
                str(current_date.month),
                str(current_date.day),
                device_name,
            )
        else:
            resource_dir = os.path.join(
                device_name,
                str(current_date.year),
                str(current_date.month),
                str(current_date.day),
            )

        filename = self._filename_provider()
        return PathInfo(
            root=self._directory_path,
            resource_dir=resource_dir,
            filename=filename,
            create_dir_depth=self._create_dir_depth,
        )


class NameProvider(Protocol):
    @abstractmethod
    def __call__(self) -> str:
        """Get the name to be used as a data_key in the descriptor document"""


class ShapeProvider(Protocol):
    @abstractmethod
    async def __call__(self) -> Sequence[int]:
        """Get the shape of the data collection"""
