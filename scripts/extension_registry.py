"""Public base and on-demand extension registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    layer: str
    purpose: str
    depends_on: tuple[str, ...] = ('core',)
    public: bool = True
    compatibility: bool = False

    def describe(self) -> dict:
        data = asdict(self)
        data['depends_on'] = list(self.depends_on)
        return data


BASE = ModuleSpec(
    module_id='core',
    layer='base',
    purpose='项目、任务、来源、证据、结构化知识与能力目录',
    depends_on=(),
)

EXTENSIONS = {
    'fs': ModuleSpec(
        module_id='fs',
        layer='extension',
        purpose='许可工作区内的只读文件访问',
    ),
    'longform': ModuleSpec(
        module_id='longform',
        layer='extension',
        purpose='长文方向、草稿、参考书与交接快照',
    ),
}

AVAILABLE = (BASE.module_id, *EXTENSIONS)
PUBLIC_MODULES = AVAILABLE


def module_spec(module_id: str) -> ModuleSpec:
    if module_id == BASE.module_id:
        return BASE
    try:
        return EXTENSIONS[module_id]
    except KeyError as exc:
        raise ValueError(f'未知模块: {module_id}') from exc


def describe_modules(selected) -> dict:
    return {
        'model': 'base_plus_extensions',
        'base': BASE.describe(),
        'extensions': [module_spec(name).describe() for name in selected if name != BASE.module_id],
    }
