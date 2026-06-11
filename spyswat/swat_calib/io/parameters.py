from pathlib import Path
from typing import Dict
from collections import defaultdict
from spyswat.swat_calib.utils.data_info import DATAParameter
from spyswat.swat_calib.io.readers import ReadFileLine


class SWATParam(ReadFileLine):
    """
    Read and manage SWAT parameter definitions.

    Parameter keys MUST use 'name.ext' format to avoid ambiguous updates
    across files that share the same parameter name (e.g. ESCO in .hru and .bsn).

    Examples:
        >>> param_file = SWATParam("swatParam.txt")
        >>> param = param_file.get("CN2.mgt")
        >>> print(param.name, param.ext, param.vmin, param.vmax)
    """

    def __init__(self, param_path):
        super().__init__()
        self.param_path = Path(param_path)
        if not self.param_path.exists():
            raise FileNotFoundError(f"Parameter file not found: {param_path}")
        self.params = self.__read_param_file(str(param_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> DATAParameter:
        """
        Retrieve parameter definition.

        Args:
            name: Must be 'name.ext' format, e.g. 'CN2.mgt', 'ALPHA_BF.gw'.
                  Bare names like 'CN2' are rejected to prevent updating the
                  wrong file when the same parameter exists in multiple extensions.

        Raises:
            KeyError: If name is not in 'name.ext' format, or not found.
        """
        if '.' not in name:
            # Helpful hint: show which keys exist for this bare name
            candidates = [k for k, v in self.params.items() if v.name == name]
            if candidates:
                raise KeyError(
                    f"Parameter '{name}' requires file extension. "
                    f"Use one of: {candidates}"
                )
            raise KeyError(
                f"Parameter '{name}' not found. "
                f"Use 'name.ext' format, e.g. 'CN2.mgt'."
            )

        if name not in self.params:
            raise KeyError(
                f"Parameter '{name}' not found in param file. "
                f"Available keys: {list(self.params.keys())}"
            )
        return self.params[name]

    def get_params(self, param: list) -> Dict:
        """Group a list of 'name.ext' keys by extension."""
        param_by_ext = defaultdict(list)
        for pname in param:
            param_ = self.get(pname)          # raises if bare name
            ext = param_.ext if param_.ext.startswith('.') else f".{param_.ext}"
            param_by_ext[ext].append(pname)
        return dict(param_by_ext)

    def get_param_by_name(self, param_dict: Dict) -> Dict:
        """Group a {name.ext: value} dict by extension."""
        param_by_ext = defaultdict(dict)
        for pname, value in param_dict.items():
            param = self.get(pname)           # raises if bare name
            ext = param.ext if param.ext.startswith('.') else f".{param.ext}"
            param_by_ext[ext][pname] = value
        return dict(param_by_ext)

    def available_keys(self) -> list:
        """Return all registered 'name.ext' keys."""
        return list(self.params.keys())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def __read_param_file(self, file_path: str) -> Dict:
        """Read parameter definition file."""
        params = {}
        lines = self.__read_file(file_path)
        for items in lines:
            full_param = items[0]
            name, ext = self.__parse_input_name(full_param)
            key = f"{name}{ext}"
            param = DATAParameter(
                name=name,
                ext=ext,
                line=int(items[1]) - 1,   # Python 0-indexed
                start=int(items[2]) - 1,
                end=int(items[3]),
                round=int(items[4]),
                vmin=float(items[5]),
                vmax=float(items[6])
            )
            params[key] = param
        return params

    def __read_file(self, file_path: str):
        """Read file and parse lines."""
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [
                self._split_space(line.strip())
                for line in f
                if line.strip() and not line.startswith('!')
            ]
        return lines

    def __parse_input_name(self, full_name: str):
        """Parse 'CN2.mgt' → ('CN2', '.mgt')."""
        if '.' in full_name:
            parts = full_name.rsplit('.', 1)
            return parts[0], f".{parts[1]}"
        return full_name, ''

    def __repr__(self):
        return f"SWATParam(params={len(self.params)})"
