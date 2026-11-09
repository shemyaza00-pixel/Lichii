#!/usr/bin/env python3
"""Apply the AMD unwritten-render-target fix from zortos293/Lichii issue #323
to the exact Fritchii v5.5 sources. Fail loudly if upstream context changes.
No audio or shader precompilation code is modified.
"""
from pathlib import Path

def replace_once(path, old, new):
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one anchor; found {count}: {old[:90]!r}")
    p.write_text(s.replace(old, new), encoding="utf-8")
    print(f"Patched {path}: {old[:60]!r}")

root = "src/video_core/renderer_vulkan/"
replace_once(root + "vk_graphics_pipeline.cpp",
    "    fragment_has_color0_output = stage_infos[NUM_STAGES - 1].stores_frag_color[0];\n",
    """    fragment_has_color0_output = stage_infos[NUM_STAGES - 1].stores_frag_color[0];
    // An unwritten render target has undefined color in Vulkan. AMD can write
    // garbage at the mountain/sky edge (Lichii issue #323). Disable its writes.
    if (infos[NUM_STAGES - 1]) {
        color_output_mask = 0;
        for (size_t rt = 0; rt < 8; ++rt) {
            if (stage_infos[NUM_STAGES - 1].stores_frag_color[rt]) {
                color_output_mask |= static_cast<u8>(1U << rt);
            }
        }
    }
""")
replace_once(root + "vk_graphics_pipeline.cpp",
    """            write_mask |= mask[i] ? mask_table[i] : 0;
        }
        cb_attachments.push_back({""",
    """            write_mask |= mask[i] ? mask_table[i] : 0;
        }
        if ((color_output_mask & (1U << index)) == 0) {
            write_mask = 0;
        }
        cb_attachments.push_back({""")
replace_once(root + "vk_graphics_pipeline.h",
    """    bool SupportsAlphaToCoverage() const noexcept {""",
    """    /// Bit i is set when the fragment shader writes render target i.
    u8 ColorOutputMask() const noexcept {
        return color_output_mask;
    }

    bool SupportsAlphaToCoverage() const noexcept {""")
replace_once(root + "vk_graphics_pipeline.h",
    "    bool fragment_has_color0_output{};\n",
    "    bool fragment_has_color0_output{};\n    u8 color_output_mask{0xff};\n")
replace_once(root + "vk_rasterizer.cpp",
    """    if (device.IsExtExtendedDynamicState3BlendingSupported()) {
        UpdateBlending(regs);
    } else if (device.IsExtColorWriteEnableSupported()) {""",
    """    if (device.IsExtExtendedDynamicState3BlendingSupported()) {
        const GraphicsPipeline* gp =
            draw_pipeline != nullptr ? draw_pipeline : pipeline_cache.CurrentGraphicsPipeline();
        const u8 outputs = gp ? gp->ColorOutputMask() : u8{0xff};
        if (outputs != last_color_output_mask) {
            last_color_output_mask = outputs;
            flags[Dirty::Blending] = true;
            flags[Dirty::ColorMask] = true;
        }
        UpdateBlending(regs);
    } else if (device.IsExtColorWriteEnableSupported()) {""")
replace_once(root + "vk_rasterizer.cpp",
    """            if (mask.A) {
                current |= VK_COLOR_COMPONENT_A_BIT;
            }
        }
        scheduler.Record([setup_masks]""",
    """            if (mask.A) {
                current |= VK_COLOR_COMPONENT_A_BIT;
            }
            if ((last_color_output_mask & (1U << index)) == 0) {
                current = 0;
            }
        }
        scheduler.Record([setup_masks]""")
replace_once(root + "vk_rasterizer.h",
    """    void UpdateBlending(Tegra::Engines::Maxwell3D::Regs& regs);
    void UpdateColorWriteEnable""",
    """    void UpdateBlending(Tegra::Engines::Maxwell3D::Regs& regs);
    u8 last_color_output_mask{0xff};
    void UpdateColorWriteEnable""")
# Fritchii v5.5 uses a local variable named 'values' in settings functions.
# Its upstream MSVC flags mark shadow warnings (C4459) as errors; renaming a
# local identifier fixes the build without changing the settings behavior.
import re
settings_path = Path("src/common/frizti_settings.cpp")
settings_text = settings_path.read_text(encoding="utf-8")
settings_text, renamed = re.subn(r"\bvalues\b", "local_values", settings_text)
if renamed < 6:
    raise RuntimeError(f"Unexpected local settings variable count: {renamed}")
settings_path.write_text(settings_text, encoding="utf-8")
print(f"Renamed {renamed} local settings references for MSVC build compatibility")
print("Applied four-file #323 graphics fix plus settings identifier rename (no semantic change)")
