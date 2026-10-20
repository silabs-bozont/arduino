import json
import os
import shutil
import subprocess
import sys

"""
Little helper script to generate and optionally build platform support GSDK files/archives for Arduino with SLC
"""

# To customize/configure generation, please edit the 'generate_gsdk.cfg' file to your preferences
config_file_path = "generate_gsdk.cfg"
gsdk_dir = None
slc_output_dir = None
gsdk_version = None
matter_extension_version = None
matter_extension_dir = None
aiml_extension_version = None
aiml_extension_dir = None
slc_cli = "slc"
zap_cli = None
arduino_gcc_dir = None

gsdk_cpp_empty_folder = "app/common/example/empty/"
# Staged Matter SLCP workspace (symlinks into matter_extension_dir; never writes origin)
matter_workspace_dir = "matter_workspace/"
matter_workspace_slcp_rel = "slc/apps/arduino/"
gsdk_license_file = "gsdk_license"
variants_folder = "../variants/"


def main():
    print()
    print("Arduino GSDK generator/prebuilder")
    print("-" * 33)

    read_config_file(config_file_path)

    current_platform_config = get_platform_config_from_arguments()
    if current_platform_config["name"] == "all":
        # Get all the platform configurations and remove the first three (which are the "all" configs)
        all_platform_configs = platform_configurations[7:]
        for config in all_platform_configs:
            generate_gsdk(config)
    elif current_platform_config["name"] == "precomp_all":
        # Generate all the precomp platform configurations
        all_platform_configs = platform_configurations[7:]
        for config in all_platform_configs:
            if config["prebuild"]:
                generate_gsdk(config)
    elif current_platform_config["name"] == "noradio_precomp_all":
        # Generate all the noradio platform configurations
        noradio_all_platform_configs = platform_configurations[7:]
        for config in noradio_all_platform_configs:
            if config["protocol_stack"] == 'noradio' and config["prebuild"]:
                generate_gsdk(config)
    elif current_platform_config["name"] == "ble_arduino_precomp_all":
        # Generate all the ble (controller) platform configurations
        ble_all_platform_configs = platform_configurations[7:]
        for config in ble_all_platform_configs:
            if config["protocol_stack"] == 'ble_arduino' and config["prebuild"]:
                generate_gsdk(config)
    elif current_platform_config["name"] == "ble_silabs_precomp_all":
        # Generate all the ble (silabs host) platform configurations
        ble_silabs_all_platform_configs = platform_configurations[7:]
        for config in ble_silabs_all_platform_configs:
            if config["protocol_stack"] == 'ble_silabs' and config["prebuild"]:
                generate_gsdk(config)
    elif current_platform_config["name"] == "matter_precomp_all":
        # Generate all the matter platform configurations
        matter_all_platform_configs = platform_configurations[7:]
        for config in matter_all_platform_configs:
            if config["protocol_stack"] == 'matter' and config["prebuild"]:
                generate_gsdk(config)
    elif current_platform_config["name"] == "zigbee_precomp_all":
        # Generate all the zigbee platform configurations
        zigbee_all_platform_configs = platform_configurations[7:]
        for config in zigbee_all_platform_configs:
            if config["protocol_stack"] == 'zigbee' and config["prebuild"]:
                generate_gsdk(config)
    else:
        generate_gsdk(current_platform_config)


def generate_gsdk(current_platform_config):
    """
    The main entry point of the GSDK generator
    Generates GSDK with the provided config
    """
    config_name = current_platform_config["name"]
    arduino_variant_name = current_platform_config["arduino_variant_name"]
    prebuild = current_platform_config["prebuild"]
    additional_files = current_platform_config["additional_files"]
    protocol_stack = current_platform_config["protocol_stack"]
    project_slcp_file = current_platform_config["slcp_file"]
    board_opn = current_platform_config["board_opn"]
    ai_capable = current_platform_config["ai_capable"]
    if protocol_stack == 'matter':
        matter_project_zap_file = current_platform_config["matter_zap_file"]
    if protocol_stack == 'zigbee':
        zigbee_project_zap_file = current_platform_config["zigbee_zap_file"]

    output_dir = "gen_gsdk_" + config_name + "/"
    slcp_file_name = os.path.basename(project_slcp_file)
    variant_target_folder = variants_folder + arduino_variant_name + "/" + protocol_stack + "/"

    print()
    print("-" * 50)
    print(f"Name: {config_name}")
    print(f"Arduino variant: {arduino_variant_name}")
    print(f"Board: {board_opn}")
    print(f"AI capable: {ai_capable}") # Indicates if the board supports hardware acceleration for AI/ML tasks
    if ai_capable:
        print(f"AI/ML extension version: {aiml_extension_version}")
    print(f"Project file: {slcp_file_name}")
    print(f"Prebuild: {prebuild}")
    print(f"Protocol stack: {protocol_stack}")
    if protocol_stack == 'matter':
        print(f"Matter ZAP file: {matter_project_zap_file}")
    if protocol_stack == 'zigbee':
        print(f"Zigbee ZAP file: {zigbee_project_zap_file}")
    print(f"GSDK dir: {gsdk_dir}")
    print(f"GSDK version: {gsdk_version}")
    if protocol_stack == 'matter':
        print(f"Matter extension version: {matter_extension_version}")
    print(f"Output dir: {output_dir}")
    if prebuild:
        print(f"Variant target folder: {variant_target_folder}")
    print("-" * 50)

    is_noradio = (protocol_stack == 'noradio')
    is_ble_arduino = (protocol_stack == 'ble_arduino')
    is_ble_silabs = (protocol_stack == 'ble_silabs')
    is_matter = (protocol_stack == 'matter')
    is_zigbee = (protocol_stack == 'zigbee')

    # All current stacks generate from package SLCP (SiSDK 2026.x); never write into the origin SDK tree
    use_direct_slcp_generate = is_noradio or is_ble_silabs or is_ble_arduino or is_zigbee or is_matter
    slcp_folder = None
    matter_staged_slcp = None

    if use_direct_slcp_generate:
        if is_zigbee:
            prepare_zigbee_zap_for_project(project_slcp_file, zigbee_project_zap_file)
        if is_matter:
            matter_staged_slcp = prepare_matter_workspace_for_project(
                project_slcp_file, matter_project_zap_file, additional_files
            )
        generate_project_with_slc_direct(
            matter_staged_slcp if is_matter else project_slcp_file,
            board_opn,
            config_name,
            is_ble_arduino=is_ble_arduino,
            is_zigbee=is_zigbee,
            is_matter=is_matter,
        )
        if is_matter:
            # -cpsdk leaves SLCP include/source as broken ../ relative paths;
            # materialize Arduino Matter app files into gen/ like classic SLC did.
            materialize_matter_arduino_project_files()
    else:
        slcp_folder = gsdk_cpp_empty_folder
        copy_slcp_file(slcp_folder, project_slcp_file, additional_files)
        generate_project_with_slc(slcp_folder, slcp_file_name, board_opn)

    patch_peripheral_inits()
    if is_ble_arduino:
        patch_ble_arduino_stack_init()
    if is_zigbee:
        patch_zigbee_includes()
    if prebuild:
        patch_makefiles()
    if is_matter:
        patch_matter_max_dynamic_endpoint_count()
        patch_matter_device_descriptors(current_platform_config["matter_vendor_name"], current_platform_config["matter_vendor_id"])
        patch_matter_device_name()
        patch_matter_time_sync_tsc_feature()
        patch_matter_attribute_singleton_flag()
        patch_matter_config_for_arduino()
        patch_matter_attribute_largest_for_dynamic_endpoints()
    build_project()
    if is_matter:
        # Variant provides the strong StartAppTask stub; weaken gsdk.a's lighting-app symbol.
        weaken_matter_start_app_task_in_archive(os.path.join(slc_output_dir, "gsdk.a"))
    apply_license_to_unlicensed_files(slc_output_dir + "autogen")
    apply_license_to_unlicensed_files(slc_output_dir + "config")
    if prebuild:
        copy_output_files_prebuild(output_dir, is_matter, is_ble_arduino, is_noradio, ai_capable, is_zigbee)
        copy_generated_sdk_to_variants(output_dir, variant_target_folder)
    else:
        copy_output_files(output_dir, is_matter)

    keep_gen_folder = get_keep_gen_folder_parameter_from_arguments()
    if use_direct_slcp_generate:
        cleanup_direct_generate(keep_gen_folder)
    else:
        cleanup(slcp_folder, slcp_file_name, additional_files, keep_gen_folder)

    print(f"Output location: {output_dir}")
    print("Finished!")


def copy_slcp_file(gsdk_soc_empty_folder, project_slcp_file, additional_files):
    """
    Copy the slcp file to the soc_empty example folder
    """
    print("Copying slcp file...")
    shutil.copy(project_slcp_file, gsdk_dir + gsdk_soc_empty_folder)

    print("Copying additional files...")
    for file in additional_files:
        # If the current element is a list - extract the filename and target directory and copy there
        if type(file) == list:
            shutil.copy(file[0], gsdk_dir + file[1])
        else:
            shutil.copy(file, gsdk_dir + gsdk_soc_empty_folder)


def generate_project_with_slc(gsdk_soc_empty_folder, slcp_file_name, board_opn):
    """
    Generate with SLC after copying the SLCP into an SDK example tree (Matter / Zigbee)
    """
    print("Starting SLC generation...")

    # Remove the target directory if it exists
    if os.path.exists(slc_output_dir) and os.path.isdir(slc_output_dir):
        shutil.rmtree(slc_output_dir)

    # Call slc to generate the project
    slc_process = subprocess.Popen(
        [slc_cli, "generate", "-o", "makefile", "-tlcn", "gcc", "-cp", "--generator-timeout", "600",
         "-s", gsdk_dir, "-p", gsdk_dir+gsdk_soc_empty_folder+slcp_file_name, "-d", slc_output_dir, "--with", board_opn]
    )
    slc_process.communicate(timeout=600)
    print("SLC generation finished")


def trust_sdk():
    """
    Trust the configured SDK with the pinned slc-cli.
    Sibling extensions are supplied via --sdk-package-path (auto-trusted for that command).
    """
    print("Trusting SDK...")
    subprocess.run([slc_cli, "signature", "trust", "-s", gsdk_dir], check=False)


def find_zap_adapter_pack_dir():
    """
    Resolve the ZAP adapter-pack root (directory containing apack.json) from zap_cli
    """
    if not zap_cli:
        return None
    zap_path = os.path.abspath(zap_cli)
    candidates = [
        os.path.dirname(zap_path),
        os.path.abspath(os.path.join(os.path.dirname(zap_path), "..", "..", "..")),  # .../zap.app/Contents/MacOS -> .../zap
        os.path.abspath(os.path.join(os.path.dirname(zap_path), "..")),
    ]
    for cand in candidates:
        if os.path.isfile(os.path.join(cand, "apack.json")):
            return cand
    return None


def rewrite_zigbee_zap_sdk_packages(zap_file_path):
    """
    Point .zap package entries at the configured SiSDK zigbee ZCL / gen-templates.
    Does not modify the origin SDK — only the package-local .zap file.
    """
    zcl_path = os.path.join(gsdk_dir, "zigbee", "app", "zcl", "zcl-zap.json")
    gen_path = os.path.join(gsdk_dir, "zigbee", "app", "framework", "gen-template", "gen-templates.json")
    if not os.path.exists(zcl_path) or not os.path.exists(gen_path):
        print(f"Missing Zigbee ZAP metadata under SDK:\n  {zcl_path}\n  {gen_path}")
        exit(-1)
    data = bind_zap_packages(zap_file_path, zcl_path, gen_path)
    write_zap_json(zap_file_path, data)
    print(f"Bound Zigbee ZAP packages to SDK {gsdk_version}: {zap_file_path}")


def prepare_zigbee_zap_for_project(project_slcp_file, zigbee_zap_file):
    """
    Install the shared Arduino Zigbee .zap next to the board SLCP (config/zcl/zcl_config.zap)
    and rebind its package paths to the configured SiSDK.
    """
    project_dir = os.path.dirname(os.path.abspath(project_slcp_file))
    dest_dir = os.path.join(project_dir, "config", "zcl")
    dest_zap = os.path.join(dest_dir, "zcl_config.zap")
    os.makedirs(dest_dir, exist_ok=True)

    src_zap = os.path.abspath(zigbee_zap_file)
    if not os.path.exists(src_zap):
        print(f"Zigbee ZAP file not found: {src_zap}")
        exit(-1)

    shutil.copy(src_zap, dest_zap)
    rewrite_zigbee_zap_sdk_packages(dest_zap)
    # Keep the shared source in sync with the board copy's feature level / schema
    if os.path.abspath(src_zap) != os.path.abspath(dest_zap):
        shutil.copy(dest_zap, src_zap)
        print(f"Updated shared Zigbee ZAP: {src_zap}")


def rewrite_matter_zap_sdk_packages(zap_file_path):
    """
    Point Matter .zap package entries at the configured Matter extension zap-templates.
    Does not modify the origin extension — only the package-local / staged .zap file.
    """
    if not matter_extension_dir:
        print("matter_extension_dir is not set; cannot bind Matter ZAP packages")
        exit(-1)

    zcl_path = os.path.join(matter_extension_dir, "src", "app", "zap-templates", "zcl", "zcl.json")
    gen_path = os.path.join(matter_extension_dir, "src", "app", "zap-templates", "app-templates.json")
    if not os.path.exists(zcl_path) or not os.path.exists(gen_path):
        print(f"Matter ZAP templates not found under {matter_extension_dir}")
        exit(-1)

    zap = bind_zap_packages(zap_file_path, zcl_path, gen_path, feature_level=110)

    # Matter 2.9 CodegenIntegration asserts Basic Information (0x0028) is only on
    # endpoint 0. Disable it on non-root endpoint types used by the Arduino template.
    root_type_indices = {
        ep.get("endpointTypeIndex")
        for ep in zap.get("endpoints", [])
        if ep.get("endpointId") == 0
    }
    disabled_basic_info = 0
    for i, ept in enumerate(zap.get("endpointTypes", [])):
        if i in root_type_indices:
            continue
        for cluster in ept.get("clusters", []):
            if cluster.get("code") == 40 and cluster.get("enabled") == 1:
                cluster["enabled"] = 0
                disabled_basic_info += 1

    write_zap_json(zap_file_path, zap)
    print(f"Bound Matter ZAP packages to extension {matter_extension_version}: {zap_file_path}")
    if disabled_basic_info:
        print(f"Disabled Basic Information on {disabled_basic_info} non-root endpoint type(s)")


def prepare_matter_workspace_for_project(project_slcp_file, matter_zap_file, additional_files):
    """
    Stage a Matter SLCP workspace that mirrors extension-relative paths
    (../../../../third_party/...) without writing into the origin Matter extension.
    Returns the absolute path of the staged SLCP.
    """
    if not matter_extension_dir or not os.path.isdir(matter_extension_dir):
        print(f"matter_extension_dir missing: {matter_extension_dir}")
        exit(-1)

    workspace = os.path.abspath(matter_workspace_dir)
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace)

    # Symlink extension trees needed by SLCP relative paths
    for name in ("third_party", "src", "slc", "provision.mattpconf"):
        src = os.path.join(os.path.abspath(matter_extension_dir), name)
        dst = os.path.join(workspace, name)
        if not os.path.exists(src):
            print(f"Missing in Matter extension: {src}")
            exit(-1)
        os.symlink(src, dst)

    for name in ("matter.slce", "matter.slsdk"):
        src = os.path.join(os.path.abspath(matter_extension_dir), name)
        dst = os.path.join(workspace, name)
        if os.path.exists(src) and not os.path.exists(dst):
            os.symlink(src, dst)

    slcp_dir = os.path.join(workspace, matter_workspace_slcp_rel)
    os.makedirs(slcp_dir, exist_ok=True)

    staged_slcp = os.path.join(slcp_dir, os.path.basename(project_slcp_file))
    shutil.copy(os.path.abspath(project_slcp_file), staged_slcp)

    package_slcp_dir = os.path.dirname(os.path.abspath(project_slcp_file))
    for name in (
        "sl_spidrv_eusart_xg24explorerkit1_config.h",
        "sl_iostream_eusart_xg24explorerkit1_config.h",
    ):
        src = os.path.join(package_slcp_dir, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(slcp_dir, name))

    matter_ble = os.path.abspath(os.path.join("slcp", "common", "MatterBLE.h"))
    if os.path.exists(matter_ble):
        shutil.copy(matter_ble, os.path.join(slcp_dir, "MatterBLE.h"))

    for file in additional_files:
        if type(file) == list:
            src = file[0]
            if os.path.exists(src):
                shutil.copy(src, os.path.join(slcp_dir, os.path.basename(src)))
        else:
            if os.path.exists(file):
                shutil.copy(file, os.path.join(slcp_dir, os.path.basename(file)))

    zap_dest_dir = os.path.join(slcp_dir, "config", "zcl")
    os.makedirs(zap_dest_dir, exist_ok=True)
    zap_dest = os.path.join(zap_dest_dir, "zcl_config.zap")
    src_zap = os.path.abspath(matter_zap_file)
    if not os.path.exists(src_zap):
        print(f"Matter ZAP file not found: {src_zap}")
        exit(-1)
    shutil.copy(src_zap, zap_dest)
    rewrite_matter_zap_sdk_packages(zap_dest)
    if os.path.abspath(src_zap) != os.path.abspath(zap_dest):
        shutil.copy(zap_dest, src_zap)
        print(f"Updated shared Matter ZAP: {src_zap}")

    print(f"Staged Matter workspace SLCP: {staged_slcp}")
    return staged_slcp


def generate_project_with_slc_direct(project_slcp_file, board_opn, project_name,
                                     is_ble_arduino=False, is_zigbee=False, is_matter=False):
    """
    Generate directly from an SLCP under package/ (SiSDK 2026.x).
    Uses -cpsdk -np and --sdk-package-path for sibling extensions (AIML, Matter, arduino_ble_hci).
    For Zigbee/Matter, passes --tool-path so SLC uses the configured ZAP adapter pack (not PATH).
    """
    print("Starting SLC generation (direct from package SLCP)...")

    project_slcp_abs = os.path.abspath(project_slcp_file)
    slc_output_abs = os.path.abspath(slc_output_dir)

    if os.path.exists(slc_output_abs) and os.path.isdir(slc_output_abs):
        shutil.rmtree(slc_output_abs)

    trust_sdk()

    sdk_package_paths = os.path.abspath(gsdk_dir.rstrip("/"))
    if aiml_extension_dir:
        sdk_package_paths = sdk_package_paths + "," + os.path.abspath(aiml_extension_dir.rstrip("/"))
    if is_matter:
        if not matter_extension_dir or not os.path.isdir(matter_extension_dir):
            print(f"Matter generation requires matter_extension_dir in generate_gsdk.cfg (got: {matter_extension_dir})")
            exit(-1)
        sdk_package_paths = sdk_package_paths + "," + os.path.abspath(matter_extension_dir.rstrip("/"))
    if is_ble_arduino:
        # HCI reset + ArduinoBLE name/compat without bluetooth_hci RCP/UART
        arduino_ble_hci_ext = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "slcp", "common", "arduino_ble_hci")
        )
        if not os.path.isdir(arduino_ble_hci_ext):
            print(f"Missing arduino_ble_hci extension at {arduino_ble_hci_ext}")
            exit(-1)
        sdk_package_paths = sdk_package_paths + "," + arduino_ble_hci_ext

    generator_timeout = "1800" if is_matter else "600"
    cmd = [
        slc_cli, "generate",
        "-o", "makefile",
        "-tlcn", "gcc",
        "-cpsdk",
        "-np",
        "--overwrite-all",
        "--force",
        "--generator-timeout", generator_timeout,
        "--sdk-package-path", sdk_package_paths,
        "-p", project_slcp_abs,
        "-d", slc_output_abs,
        "-name", project_name,
        "--with", board_opn,
    ]

    if is_zigbee or is_matter:
        if not zap_cli or not os.path.exists(zap_cli):
            print(f"Zigbee/Matter generation requires zap_cli in generate_gsdk.cfg (got: {zap_cli})")
            exit(-1)
        zap_adapter = find_zap_adapter_pack_dir()
        if not zap_adapter:
            print(f"Could not find ZAP apack.json near zap_cli: {zap_cli}")
            exit(-1)
        cmd.extend(["--tool-path", zap_adapter])
        print(f"Using ZAP adapter pack: {zap_adapter}")
        print(f"Using zap_cli: {zap_cli}")

    print("SLC command: " + " ".join(cmd))
    env = os.environ.copy()
    # Prefer configured ZAP over anything on PATH when SLC/post-gen invokes it
    if zap_cli and os.path.exists(zap_cli):
        env["PATH"] = os.path.dirname(os.path.abspath(zap_cli)) + os.pathsep + env.get("PATH", "")
    # Matter generate can be long
    timeout = 2400 if is_matter else 1200
    slc_process = subprocess.Popen(cmd, env=env)
    slc_process.communicate(timeout=timeout)
    if slc_process.returncode != 0:
        print(f"SLC generation failed with exit code {slc_process.returncode}")
        exit(-1)
    print("SLC generation finished")


def find_type_of_file_in_dir(file_extension, dir):
    """
    Finds the first file with the given extension in the provided directory
    """
    ret_file = None
    for file_path in os.listdir(dir):
        # check if current file_path is a file
        if os.path.isfile(os.path.join(dir, file_path)):
            if file_path.endswith(file_extension):
                # Return with the first matching file
                ret_file = file_path
                break
    return ret_file


def replace_in_file(path, old, new, *, required=True, already_marker=None, label=None):
    """
    Idempotent text replace for gen-tree patches. Returns True if a change was written.
    If already_marker is present in the file, treat as already patched and skip.
    """
    if not os.path.exists(path):
        if required:
            print(f"Missing file for patch: {path}")
            exit(-1)
        return False
    with open(path, "r") as in_file:
        content = in_file.read()
    name = label or os.path.basename(path)
    if already_marker and already_marker in content:
        print(f"{name}: already patched")
        return False
    if old not in content:
        if required:
            print(f"{name}: could not locate expected text to patch")
            exit(-1)
        return False
    with open(path, "w") as out_file:
        out_file.write(content.replace(old, new, 1))
    print(f"Patched {name}")
    return True


def bind_zap_packages(zap_file_path, zcl_path, gen_path, *, feature_level=None):
    """
    Rewrite .zap package entries to absolute zcl / gen-template paths.
    Optional feature_level override (Matter). Returns the loaded zap dict.
    """
    with open(zap_file_path, "r") as f:
        data = json.load(f)
    if feature_level is not None:
        data["featureLevel"] = feature_level
    packages = []
    for pkg in data.get("package", []):
        pkg = dict(pkg)
        ptype = pkg.get("type")
        if ptype == "zcl-properties":
            pkg["path"] = os.path.abspath(zcl_path)
            pkg["pathRelativity"] = "absolute"
        elif ptype == "gen-templates-json":
            pkg["path"] = os.path.abspath(gen_path)
            pkg["pathRelativity"] = "absolute"
        packages.append(pkg)
    data["package"] = packages
    return data


def write_zap_json(zap_file_path, data):
    with open(zap_file_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def matter_gen_path(*parts):
    """Path under the staged/copied Matter SDK tree inside slc_output_dir."""
    return os.path.join(slc_output_dir, "matter_" + matter_extension_version, *parts)


def patch_peripheral_inits():
    """
    Removes the peripheral initialization calls from the generated project.
    The GSDK automatically initializes all included peripherals - but Arduino has a different philosophy.
    By patching these out the peripherals won't be initialized after boot - only when the user requests them.
    """
    event_handler_file_path = "/autogen/sl_event_handler.c"

    with open(slc_output_dir + event_handler_file_path, "r") as in_file:
        buf = in_file.readlines()

    with open(slc_output_dir + event_handler_file_path, "w") as out_file:
        for line in buf:
            if "sl_debug_swo_init();" in line:
                 line = "  //" + line
            if "sl_cos_send_config();" in line:
                line = "  //" + line
            if "sl_i2cspm_init_instances();" in line:
                 line = "  //" + line
            if "sl_spidrv_init_instances();" in line:
                 line = "  //" + line
            if "sl_iostream_init_instances();" in line:
                line = "  //" + line
            if "sl_iostream_uart_init_instances();" in line:
                 line = "  //" + line
            if "sl_iostream_usart_init_instances();" in line:
                 line = "  //" + line
            if "sl_iostream_eusart_init_instances();" in line:
                 line = "  //" + line
            if "sl_rail_util_pti_init();" in line:
                 line = "  //" + line
            if "sl_pwm_init_instances();" in line:
                line = "  //" + line
            if "sl_simple_led_init_instances();" in line:
                line = "  //" + line
            if "sl_tflite_micro_init();" in line:
                line = "  //" + line
            out_file.write(line)
    print("Patched peripheral initialization calls")


def patch_zigbee_includes():
    """
    Zigbee AF plugin token headers include \"config/<plugin>-config.h\"
    SLC -cpsdk makefiles add -Iconfig but not -I. (project root); add it.
    """
    mak_file = find_type_of_file_in_dir(".mak", slc_output_dir)
    if not mak_file:
        return
    mak_path = slc_output_dir + mak_file
    with open(mak_path, "r") as in_file:
        buf = in_file.readlines()

    patched = False
    with open(mak_path, "w") as out_file:
        for line in buf:
            # SLC emits either "INCLUDES +=" or "INCLUDES += \"
            if (not patched) and line.lstrip().startswith("INCLUDES +="):
                out_file.write(line)
                out_file.write(" -I. \\\n")
                patched = True
                continue
            out_file.write(line)
    if patched:
        print("Patched Zigbee includes: added -I. for config/<plugin>-config.h")


def patch_ble_arduino_stack_init():
    """
    For BLE (Arduino)/HCI: leave controller init to ArduinoBLE's HCISilabsTransport.
    Keep sl_btctrl_rtos_init() so the link-layer task exists; skip sl_btctrl_init()
    here so feature/HCI init is not done twice before HCI reset.
    """
    event_handler_file_path = slc_output_dir + "/autogen/sl_event_handler.c"
    if not os.path.exists(event_handler_file_path):
        return

    with open(event_handler_file_path, "r") as in_file:
        buf = in_file.readlines()

    patched = False
    with open(event_handler_file_path, "w") as out_file:
        for line in buf:
            # Match sl_btctrl_init(); but not sl_btctrl_init_*(feature) or rtos_init
            stripped = line.strip()
            if stripped == "sl_btctrl_init();" or stripped == "sl_bt_controller_init();":
                line = "  // ArduinoBLE owns controller init (HCISilabsTransport::begin)\n  //" + line.lstrip()
                patched = True
            out_file.write(line)
    if patched:
        print("Patched ble_arduino stack init: deferred sl_btctrl_init to ArduinoBLE")


def patch_makefiles():
    """
    Patch the makefiles to output an archive of the GSDK instead of a binary
    """
    # Find the first .Makefile in the directory
    print("Patching the makefiles...")
    makefile = find_type_of_file_in_dir(".Makefile", slc_output_dir)
    makefile_path = slc_output_dir + makefile

    # Patch in the archive building
    with open(makefile_path, "r") as in_file:
        buf = in_file.readlines()

    already_patched = any("$(AR) rcs gsdk.a $(OBJS)" in line for line in buf)
    linecnt = 0
    with open(makefile_path, "w") as out_file:
        for line in buf:
            # Skip post-build — we never produce .s37 when linking is disabled
            if "pre-build $(OUTPUT_DIR)/$(PROJECTNAME).out post-build" in line:
                line = line.replace(" post-build", "")
            # Add archive file generation to the build process (idempotent)
            if (not already_patched) and "@echo $(OBJS) > $(OUTPUT_DIR)/linker_objs" in line:
                line = line + "\t$(ECHO)$(AR) rcs gsdk.a $(OBJS)\n"
            # Comment out the linking phase and the binary conversion so that the build won't fail
            # (cosmetic only, we don't need it to link, we have the archive before that)
            if line.lstrip().startswith("$(ECHO)$(LD) $(LD_FLAGS) @$(OUTPUT_DIR)/linker_objs $(LIBS) -o $(OUTPUT_DIR)/$(PROJECTNAME).out"):
                line = "#" + line
                for offset in (1, 2, 3):
                    if linecnt + offset < len(buf) and not buf[linecnt + offset].lstrip().startswith("#"):
                        buf[linecnt + offset] = "#" + buf[linecnt + offset]
            out_file.write(line)
            linecnt += 1

    # Find the first .mak in the directory
    mak_file = find_type_of_file_in_dir(".mak", slc_output_dir)

    # Patch out the build of 'main.c' and 'app.c' - we don't need their symbols in the archive
    with open(slc_output_dir + mak_file, "r") as in_file:
        buf = in_file.readlines()

    linecnt = 0
    with open(slc_output_dir + mak_file, "w") as out_file:
        for line in buf:
            # If we find the build recipe for these files, comment them out and the next 5 lines as well
            aiml_tflite_init_recipe = (
                f"$(OUTPUT_DIR)/project/aiml_{aiml_extension_version}/src/sl_tflite_micro_init.o: "
                f"aiml_{aiml_extension_version}/src/sl_tflite_micro_init.cc"
            )
            if (("$(OUTPUT_DIR)/project/main.o: main.c" in line) or
                ("$(OUTPUT_DIR)/project/app.o: app.c" in line) or
                ("$(OUTPUT_DIR)/project/src/main.o: src/main.cpp" in line) or
                ("$(OUTPUT_DIR)/project/src/AppTask.o: src/AppTask.cpp" in line) or
                ("$(OUTPUT_DIR)/project/src/LightingManager.o: src/LightingManager.cpp" in line) or
                ("$(OUTPUT_DIR)/project/src/ZclCallbacks.o: src/ZclCallbacks.cpp" in line) or
                # Matter 2.9 platform main — Arduino core owns main via --wrap=main
                ("src/main.cpp" in line and "main.o:" in line) or
                (aiml_tflite_init_recipe in line) or
                ("sl_tflite_micro_init.o:" in line and "sl_tflite_micro_init.cc" in line)
               ):
                line = "#" + line
                buf[linecnt + 1] = "#" + buf[linecnt + 1]
                buf[linecnt + 2] = "#" + buf[linecnt + 2]
                buf[linecnt + 3] = "#" + buf[linecnt + 3]
                buf[linecnt + 4] = "#" + buf[linecnt + 4]
                buf[linecnt + 5] = "#" + buf[linecnt + 5]

            out_file.write(line)
            linecnt += 1

    print("Patching finished")


def patch_matter_max_dynamic_endpoint_count():
    """
    Patches a Matter config file to allow dynamic endpoints to be created
    """
    chip_device_config_file_path = "matter_" + matter_extension_version + "/third_party/matter_sdk/src/include/platform/CHIPDeviceConfig.h"
    dynamic_endpoints_num = 16

    with open(slc_output_dir + chip_device_config_file_path, "r") as in_file:
        buf = in_file.readlines()

    with open(slc_output_dir + chip_device_config_file_path, "w") as out_file:
        for line in buf:
            if "#define CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT" in line:
                 line = "#define CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT " + str(dynamic_endpoints_num) + "\n"
            out_file.write(line)
    print("Patched max number of dynamic Matter endpoints")


def _arduino_matter_runtime_externs():
    """
    Extern symbols owned by the Arduino Matter library for runtime-overridable
    root BasicInformation fallbacks (used when NVM provision data is absent)
    """
    return (
        "/* Arduino Matter library runtime-overridable properties */\n"
        "#include <stdint.h>\n"
        "#ifdef __cplusplus\n"
        "extern \"C\" {\n"
        "#endif\n"
        "extern char arduino_matter_vendor_name[33];\n"
        "extern char arduino_matter_product_name[33];\n"
        "extern char arduino_matter_hardware_version_string[33];\n"
        "extern uint16_t arduino_matter_hardware_version;\n"
        "extern char arduino_matter_software_version_string[64];\n"
        "extern uint32_t arduino_matter_software_version;\n"
        "#ifdef __cplusplus\n"
        "}\n"
        "#endif\n"
    )


def patch_matter_device_descriptors(vendor_name, vendor_id):
    """
    Patches device descriptors (like name and manufacturer) in the Matter config file
    """
    chip_device_config_file_path = "matter_" + matter_extension_version + "/third_party/matter_sdk/src/include/platform/CHIPDeviceConfig.h"
    runtime_externs = _arduino_matter_runtime_externs()

    with open(slc_output_dir + chip_device_config_file_path, "r") as in_file:
        buf = in_file.readlines()

    hw_string_externs_injected = False
    with open(slc_output_dir + chip_device_config_file_path, "w") as out_file:
        for line in buf:
            #if "#define CHIP_DEVICE_CONFIG_ENABLE_TEST_SETUP_PARAMS 1" in line:
            #    line = "#define CHIP_DEVICE_CONFIG_ENABLE_TEST_SETUP_PARAMS 0\n"
            if "#define CHIP_DEVICE_CONFIG_DEVICE_VENDOR_NAME" in line:
                 line = "#define CHIP_DEVICE_CONFIG_DEVICE_VENDOR_NAME \"" + vendor_name + "\"\n"
            if "#define CHIP_DEVICE_CONFIG_DEVICE_VENDOR_ID" in line:
                line = "#define CHIP_DEVICE_CONFIG_DEVICE_VENDOR_ID " + vendor_id + "\n"
            if "#define CHIP_DEVICE_CONFIG_DEVICE_PRODUCT_NAME" in line:
                 line = "#define CHIP_DEVICE_CONFIG_DEVICE_PRODUCT_NAME \"Matter device\"\n"
            if "#define CHIP_DEVICE_CONFIG_DEFAULT_DEVICE_HARDWARE_VERSION_STRING" in line:
                if not hw_string_externs_injected:
                    out_file.write(runtime_externs)
                    hw_string_externs_injected = True
                line = "#define CHIP_DEVICE_CONFIG_DEFAULT_DEVICE_HARDWARE_VERSION_STRING arduino_matter_hardware_version_string\n"
            if "#define CHIP_DEVICE_CONFIG_TEST_SERIAL_NUMBER" in line:
                 line = "#define CHIP_DEVICE_CONFIG_TEST_SERIAL_NUMBER \"42069\"\n"
            out_file.write(line)

    platform_config_header_path = "matter_" + matter_extension_version + "/third_party/matter_sdk/src/platform/silabs/CHIPDevicePlatformConfig.h"
    with open(slc_output_dir + platform_config_header_path, "r") as in_file:
        buf = in_file.readlines()

    # Replace compile-time TEST_* string literals with extern buffers owned by the
    # Arduino Matter library so sketches can override root BasicInformation names
    # at runtime when NVM provisioned values are absent.
    runtime_vendor_name_define = "#define CHIP_DEVICE_CONFIG_TEST_VENDOR_NAME  arduino_matter_vendor_name\n"
    runtime_product_name_define = "#define CHIP_DEVICE_CONFIG_TEST_PRODUCT_NAME arduino_matter_product_name\n"
    externs_injected = False

    with open(slc_output_dir + platform_config_header_path, "w") as out_file:
        for line in buf:
            #if "#define CHIP_DEVICE_CONFIG_ENABLE_TEST_SETUP_PARAMS 1" in line:
            #    line = "#define CHIP_DEVICE_CONFIG_ENABLE_TEST_SETUP_PARAMS 0\n"
            if "#define CHIP_DEVICE_CONFIG_TEST_VENDOR_NAME" in line:
                if not externs_injected:
                    out_file.write(runtime_externs)
                    externs_injected = True
                line = runtime_vendor_name_define
            if "#define CHIP_DEVICE_CONFIG_TEST_PRODUCT_NAME" in line:
                if not externs_injected:
                    out_file.write(runtime_externs)
                    externs_injected = True
                line = runtime_product_name_define
            out_file.write(line)

    # Software/hardware version numbers and software version string live in sl_matter_config.h
    matter_config_path = "config/sl_matter_config.h"
    with open(slc_output_dir + matter_config_path, "r") as in_file:
        buf = in_file.readlines()

    version_externs_injected = False
    with open(slc_output_dir + matter_config_path, "w") as out_file:
        for line in buf:
            if line.startswith("#define CHIP_DEVICE_CONFIG_DEVICE_SOFTWARE_VERSION "):
                if not version_externs_injected:
                    out_file.write(runtime_externs)
                    version_externs_injected = True
                line = "#define CHIP_DEVICE_CONFIG_DEVICE_SOFTWARE_VERSION arduino_matter_software_version\n"
            if line.startswith("#define CHIP_DEVICE_CONFIG_DEVICE_SOFTWARE_VERSION_STRING"):
                if not version_externs_injected:
                    out_file.write(runtime_externs)
                    version_externs_injected = True
                line = "#define CHIP_DEVICE_CONFIG_DEVICE_SOFTWARE_VERSION_STRING arduino_matter_software_version_string\n"
            if line.startswith("#define CHIP_DEVICE_CONFIG_DEFAULT_DEVICE_HARDWARE_VERSION "):
                if not version_externs_injected:
                    out_file.write(runtime_externs)
                    version_externs_injected = True
                line = "#define CHIP_DEVICE_CONFIG_DEFAULT_DEVICE_HARDWARE_VERSION arduino_matter_hardware_version\n"
            out_file.write(line)

    print("Patched Matter device descriptors")


def materialize_matter_arduino_project_files():
    """
    SLC -cpsdk does not copy SLCP include:/source: entries that resolve via the
    staged Matter workspace relative paths. Copy the Arduino Matter app headers
    and CustomerAppTask into gen/, fix makefile include paths, and add the
    CustomerAppTask build recipe. Platform main.cpp is omitted — Arduino core
    owns main via --wrap=main and calls SilabsMatterConfig::AppInit().
    """
    if not matter_extension_dir or not os.path.isdir(matter_extension_dir):
        print(f"matter_extension_dir missing for materialize: {matter_extension_dir}")
        exit(-1)

    ext = os.path.abspath(matter_extension_dir)
    lighting_include = os.path.join(
        ext, "third_party/matter_sdk/examples/lighting-app/silabs/include"
    )
    customer_dir = os.path.join(
        ext, "third_party/matter_sdk/examples/platform/silabs/customer"
    )
    matter_ble_src = os.path.abspath(os.path.join("slcp", "common", "MatterBLE.h"))

    include_dir = os.path.join(slc_output_dir, "include")
    src_dir = os.path.join(slc_output_dir, "src")
    os.makedirs(include_dir, exist_ok=True)
    os.makedirs(src_dir, exist_ok=True)

    for name in ("AppConfig.h", "AppEvent.h", "CHIPProjectConfig.h"):
        src = os.path.join(lighting_include, name)
        if not os.path.exists(src):
            print(f"Missing Matter lighting include: {src}")
            exit(-1)
        shutil.copy(src, os.path.join(include_dir, name))

    customer_hdr = os.path.join(customer_dir, "CustomerAppTask.h")
    customer_src = os.path.join(customer_dir, "CustomerAppTask.cpp")
    if not os.path.exists(customer_hdr) or not os.path.exists(customer_src):
        print(f"Missing CustomerAppTask sources under {customer_dir}")
        exit(-1)
    shutil.copy(customer_hdr, os.path.join(include_dir, "CustomerAppTask.h"))
    shutil.copy(customer_src, os.path.join(src_dir, "CustomerAppTask.cpp"))

    if os.path.exists(matter_ble_src):
        shutil.copy(matter_ble_src, os.path.join(include_dir, "MatterBLE.h"))
    else:
        print(f"Warning: MatterBLE.h not found at {matter_ble_src}")

    # Fix broken -cpsdk relative includes and ensure -Iinclude is present
    mak_file = find_type_of_file_in_dir(".mak", slc_output_dir)
    if mak_file is None:
        print("Could not find project .mak to patch Matter includes")
        exit(-1)
    mak_path = os.path.join(slc_output_dir, mak_file)
    with open(mak_path, "r") as in_file:
        buf = in_file.readlines()

    broken_include_substrings = (
        "-I../third_party/matter_sdk/examples/lighting-app/silabs/include",
        "-I../third_party/matter_sdk/examples/platform/silabs/customer",
        "-I../matter_workspace/slc/apps/arduino",
    )
    new_buf = []
    has_include_flag = False
    for line in buf:
        if any(s in line for s in broken_include_substrings):
            continue
        if line.strip() == "-Iinclude" or line.strip() == "-Iinclude \\":
            has_include_flag = True
        new_buf.append(line)

    if not has_include_flag:
        inserted = False
        for i, line in enumerate(new_buf):
            if line.startswith("INCLUDES += \\"):
                new_buf.insert(i + 1, " -Iinclude \\\n")
                inserted = True
                break
        if not inserted:
            print("Warning: could not insert -Iinclude into project makefile")

    # Inject CustomerAppTask.cpp if SLC omitted it
    customer_obj = "$(OUTPUT_DIR)/project/src/CustomerAppTask.o"
    if not any(customer_obj in line for line in new_buf):
        recipe = (
            f"\n{customer_obj}: src/CustomerAppTask.cpp\n"
            "\t@$(POSIX_TOOL_PATH)echo 'Building src/CustomerAppTask.cpp'\n"
            "\t@$(POSIX_TOOL_PATH)mkdir -p $(@D)\n"
            "\t$(ECHO)$(CXX) $(CXXFLAGS) -c -o $@ src/CustomerAppTask.cpp\n"
            f"CXXDEPS += {customer_obj[:-2]}.d\n"
            f"OBJS += {customer_obj}\n"
        )
        new_buf.append(recipe)

    with open(mak_path, "w") as out_file:
        out_file.writelines(new_buf)

    print("Materialized Matter Arduino include/src and patched project makefile")


def patch_matter_device_name():
    """
    Patches the Matter BLE device name to "Arduino Matter" (< 21 chars).
    """
    app_config_file_path = "include/AppConfig.h"
    app_config_abs = slc_output_dir + app_config_file_path
    if not os.path.exists(app_config_abs):
        print(f"AppConfig.h not found at {app_config_abs} — run materialize_matter_arduino_project_files first")
        exit(-1)

    with open(app_config_abs, "r") as in_file:
        buf = in_file.readlines()

    with open(app_config_abs, "w") as out_file:
        for line in buf:
            if "#define BLE_DEV_NAME" in line:
                 # BLEManagerImpl rejects names with strlen >= kMaxDeviceNameLength (21)
                 line = "#define BLE_DEV_NAME \"Arduino Matter\"\n"
            out_file.write(line)

    print("Patched Matter device name")


def patch_matter_time_sync_tsc_feature():
    """
    matter_time_synchronization.slcc hardcodes TIME_SYNC_ENABLE_TSC_FEATURE=1, which
    pulls in ReadClient APIs. Arduino ZAP only enables the TimeZone feature and
    CHIP_CONFIG_ENABLE_READ_CLIENT stays 0 — force TSC off so the cluster compiles.
    """
    mak_file = find_type_of_file_in_dir(".mak", slc_output_dir)
    if mak_file is None:
        print("Could not find project .mak to patch TIME_SYNC_ENABLE_TSC_FEATURE")
        exit(-1)
    mak_path = os.path.join(slc_output_dir, mak_file)
    with open(mak_path, "r") as in_file:
        content = in_file.read()
    old = "'-DTIME_SYNC_ENABLE_TSC_FEATURE=1'"
    new = "'-DTIME_SYNC_ENABLE_TSC_FEATURE=0'"
    if old not in content:
        print("TIME_SYNC_ENABLE_TSC_FEATURE=1 not found in project makefile (ok if already patched)")
        return
    with open(mak_path, "w") as out_file:
        out_file.write(content.replace(old, new))
    print("Patched TIME_SYNC_ENABLE_TSC_FEATURE=0 (TSC/ReadClient not enabled for Arduino)")


def patch_matter_config_for_arduino():
    """
    Single-pass Arduino tweaks for gen MatterConfig.cpp:
    - drop ApplicationStart from Realtime7 to Normal (avoids starving setup/loop)
    - after Server::Init, disable ZAP placeholder endpoint 2 and set ready flag
    """
    path = matter_gen_path("third_party/matter_sdk/examples/platform/silabs/MatterConfig.cpp")
    if not os.path.exists(path):
        print(f"MatterConfig.cpp not found at {path}")
        exit(-1)
    with open(path, "r") as in_file:
        content = in_file.read()

    changed = False
    if "Arduino: was Realtime7" not in content:
        old_prio = ".priority   = osPriorityRealtime7 };"
        new_prio = ".priority   = osPriorityNormal }; // Arduino: was Realtime7 (starved setup/loop)"
        if old_prio not in content:
            print("Could not locate kMainTaskAttr priority in MatterConfig.cpp")
            exit(-1)
        content = content.replace(old_prio, new_prio, 1)
        changed = True

    if "arduino_matter_server_ready = true" not in content:
        include_anchor = "#include <cmsis_os2.h>\n"
        include_patch = (
            "#include <cmsis_os2.h>\n"
            "#include <app/util/endpoint-config-api.h>\n"
            "#include <app/util/attribute-storage.h>\n"
            "\n"
            "// Declared in Arduino cores/gecko/silabs_stubs.cpp\n"
            "extern \"C\" volatile bool arduino_matter_server_ready;\n"
        )
        if include_anchor not in content:
            print("Could not locate cmsis_os2 include in MatterConfig.cpp")
            exit(-1)
        content = content.replace(include_anchor, include_patch, 1)

        old_epilogue = (
            "    ReturnErrorOnFailure(PlatformMgr().StartEventLoopTask());\n"
            "\n"
            "#ifdef ENABLE_CHIP_SHELL\n"
            "    chip::startShellTask();\n"
            "#endif\n"
            "\n"
            "    return CHIP_NO_ERROR;\n"
            "}"
        )
        new_epilogue = (
            "    ReturnErrorOnFailure(PlatformMgr().StartEventLoopTask());\n"
            "\n"
            "#ifdef ENABLE_CHIP_SHELL\n"
            "    chip::startShellTask();\n"
            "#endif\n"
            "\n"
            "    // Arduino: disable ZAP placeholder endpoint 2 after Server::Init.\n"
            "    {\n"
            "        constexpr chip::EndpointId kZapPlaceholderEndpoint = 2;\n"
            "        DeviceLayer::StackLock lock;\n"
            "        if (!emberAfEndpointEnableDisable(kZapPlaceholderEndpoint, false))\n"
            "        {\n"
            "            ChipLogError(DeviceLayer, \"Arduino: failed to disable ZAP placeholder endpoint %u\",\n"
            "                         kZapPlaceholderEndpoint);\n"
            "        }\n"
            "        else\n"
            "        {\n"
            "            ChipLogProgress(DeviceLayer, \"Arduino: disabled ZAP placeholder endpoint %u\",\n"
            "                            kZapPlaceholderEndpoint);\n"
            "        }\n"
            "    }\n"
            "    arduino_matter_server_ready = true;\n"
            "\n"
            "    return CHIP_NO_ERROR;\n"
            "}"
        )
        if old_epilogue not in content:
            print("Could not locate InitMatter epilogue in MatterConfig.cpp for placeholder disable")
            exit(-1)
        content = content.replace(old_epilogue, new_epilogue, 1)
        changed = True

    if changed:
        with open(path, "w") as out_file:
            out_file.write(content)
        print("Patched MatterConfig.cpp for Arduino (priority + ZAP placeholder)")
    else:
        print("MatterConfig.cpp already patched for Arduino")


def patch_matter_attribute_largest_for_dynamic_endpoints():
    """
    Arduino dynamic endpoints declare Descriptor list attrs up to 254 bytes.
    ZAP may emit a smaller ATTRIBUTE_LARGEST (IO buffer size); bump it so
    emberAfSetDynamicEndpoint does not reject those attributes.
    """
    path = os.path.join(slc_output_dir, "autogen", "zap-generated", "endpoint_config.h")
    if not os.path.exists(path):
        print(f"endpoint_config.h not found at {path}")
        return
    with open(path, "r") as in_file:
        content = in_file.read()
    import re
    m = re.search(r"#define ATTRIBUTE_LARGEST \((\d+)\)", content)
    if not m:
        print("ATTRIBUTE_LARGEST define not found in endpoint_config.h")
        return
    current = int(m.group(1))
    required = 254
    if current >= required:
        print(f"ATTRIBUTE_LARGEST already {current} (>= {required})")
        return
    content = content.replace(
        f"#define ATTRIBUTE_LARGEST ({current})",
        f"#define ATTRIBUTE_LARGEST ({required}) // Arduino: was {current}; sized for dynamic Descriptor lists",
        1,
    )
    with open(path, "w") as out_file:
        out_file.write(content)
    print(f"Patched ATTRIBUTE_LARGEST {current} -> {required} for dynamic endpoints")


def patch_matter_attribute_singleton_flag():
    """
    ZAP 2026.x still emits ZAP_ATTRIBUTE_MASK(SINGLETON) in endpoint_config.h, but
    Matter 2.9 removed MATTER_ATTRIBUTE_FLAG_SINGLETON. Alias it to 0 in the gen
    copy of attribute-metadata.h (never touch the origin extension).
    """
    path = matter_gen_path("third_party/matter_sdk/src/app/util/attribute-metadata.h")
    replace_in_file(
        path,
        "#define MATTER_ATTRIBUTE_FLAG_NULLABLE (0x40)\n",
        "#define MATTER_ATTRIBUTE_FLAG_NULLABLE (0x40)\n"
        "// Alias until ZAP stops emitting SINGLETON (removed from Matter masks)\n"
        "#define MATTER_ATTRIBUTE_FLAG_SINGLETON (0)\n",
        already_marker="MATTER_ATTRIBUTE_FLAG_SINGLETON",
        label="attribute-metadata.h SINGLETON alias",
    )


def build_project():
    """
    Build the generated project
    """
    print("Building the project...")
    makefile = find_type_of_file_in_dir(".Makefile", slc_output_dir)
    build_process = subprocess.Popen(
        ["make", "-f", makefile, "-j", "20"], cwd=slc_output_dir
    )
    build_process.communicate(timeout=360)
    gsdk_archive = os.path.join(slc_output_dir, "gsdk.a")
    if build_process.returncode != 0:
        # Prebuild patches disable linking/.s37; post-build may still fail even when
        # gsdk.a was produced successfully.
        if os.path.exists(gsdk_archive) and os.path.getsize(gsdk_archive) > 0:
            print(f"Make exited {build_process.returncode} but gsdk.a is present — continuing")
        else:
            raise RuntimeError(f"Build failed with exit code {build_process.returncode}")
    print("Build finished")


def apply_license_to_unlicensed_files(folder):
    """
    Applies the MIT license to any unlicensed source file found in the provided folder
    """
    mit_license = """/*
 * This file is part of the Silicon Labs Arduino Core
 *
 * The MIT License (MIT)
 *
 * Copyright 2026 Silicon Laboratories Inc. www.silabs.com
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

"""
    license_start_1 = "/***************************************************************************//**"
    license_start_2 = "/* --------------------------------------------------------------------------"
    license_start_3 = "/*"

    for (root, dirs, file) in os.walk(folder):
        # For each file
        for f in file:
            # Get the full path of the current file
            filepath = os.path.join(root, f)

            # Check if it's a source file
            is_source_file = False
            filename_lower = f.lower()
            for ext in ['.c', '.h', '.cpp', '.hpp']:
                if filename_lower.endswith(ext):
                    is_source_file = True
            if not is_source_file:
                continue

            # Open the file
            with open(filepath, 'r') as fp:
                try:
                    lines = fp.readlines()
                except UnicodeDecodeError:
                    continue
                # See if it has a license
                if (license_start_1 in lines[0]
                   or license_start_2 in lines[0]
                   or license_start_3 in lines[0]):
                    continue

                # Apply the MIT license if no license found
                print(f"Applying license to: {filepath}")
                lines.insert(0, mit_license)

            # Write the file back with the license applied
            with open(filepath, "w") as out_file:
                for line in lines:
                    out_file.write(line)


def copy_output_files(output_dir, is_matter):
    """
    Get the built stuff in one place
    """
    # remove the output dir if it exists
    if os.path.exists(output_dir) and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    os.mkdir(output_dir)

    shutil.copytree(slc_output_dir + "autogen", output_dir + "autogen")
    shutil.copytree(slc_output_dir + "config", output_dir + "config")
    shutil.copytree(slc_output_dir + "simplicity_sdk_" + gsdk_version, output_dir + "simplicity_sdk_" + gsdk_version)
    # Matter has some additional folders
    if is_matter:
        shutil.copytree(slc_output_dir + "matter_" + matter_extension_version, output_dir + "matter_" + matter_extension_version)
        shutil.copytree(slc_output_dir + "include", output_dir + "include")

    print("Applying license to GSDK folder...")
    shutil.copy(gsdk_license_file, output_dir + "simplicity_sdk_" + gsdk_version + "/LICENSE")


# FreeRTOS public headers that must not be overwritten by same-named files from
# TCPLP (sys/queue.h), OpenThread, or other SDK trees when flattening includes.
MATTER_FREERTOS_KERNEL_HEADERS = {
    "FreeRTOS.h",
    "queue.h",
    "list.h",
    "task.h",
    "semphr.h",
    "timers.h",
    "event_groups.h",
    "stream_buffer.h",
    "message_buffer.h",
    "croutine.h",
    "stack_macros.h",
    "deprecated_definitions.h",
    "mpu_prototypes.h",
    "mpu_wrappers.h",
    "portable.h",
    "projdefs.h",
    "atomic.h",
}


def matter_should_copy_flat_header(src_path_norm, dest_path):
    """
    Prefer freertos/kernel/include for FreeRTOS public headers so TCPLP's
    sys/queue.h (and similar) cannot shadow QueueHandle_t.
    """
    base = os.path.basename(src_path_norm)
    if base not in MATTER_FREERTOS_KERNEL_HEADERS:
        return True
    return "/freertos/kernel/include/" in src_path_norm


def copy_extra_sdk_headers(header_output_dir):
    """
    Copy headers that Arduino needs but SLC -cpsdk may not place in the project tree
    """
    extra_headers = [
        "platform_core/platform/common/toolchain/inc/sl_gcc_preinclude.h",
        # Legacy SiSDK layout fallback
        "platform/common/toolchain/gcc/inc/sl_gcc_preinclude.h",
        "platform/common/toolchain/inc/sl_gcc_preinclude.h",
    ]
    copied = set()
    for rel in extra_headers:
        src = os.path.join(gsdk_dir, rel)
        if os.path.exists(src):
            dst_name = os.path.basename(src)
            if dst_name in copied:
                continue
            shutil.copy(src, os.path.join(header_output_dir, dst_name))
            print(f"Copying extra SDK header '{src}'")
            copied.add(dst_name)
    if "sl_gcc_preinclude.h" not in copied:
        # Last-resort search under the SDK tree
        for root, dirs, files in os.walk(gsdk_dir):
            if "sl_gcc_preinclude.h" in files:
                src = os.path.join(root, "sl_gcc_preinclude.h")
                shutil.copy(src, os.path.join(header_output_dir, "sl_gcc_preinclude.h"))
                print(f"Copying extra SDK header '{src}'")
                copied.add("sl_gcc_preinclude.h")
                break
    if "sl_gcc_preinclude.h" not in copied:
        print("Warning: sl_gcc_preinclude.h not found in SDK - Arduino builds may fail")


def copy_cmsis_profile_headers(slc_output_dir, header_output_dir):
    """
    Preserve CMSIS profile subdirectories required by nested includes in cmsis_gcc.h
    """
    for profile in ("m-profile", "a-profile", "r-profile"):
        src = None
        for root, dirs, files in os.walk(slc_output_dir):
            if os.path.basename(root) == profile and ("cmsis" in root.lower() or "CMSIS" in root):
                src = root
                break
        if src is None:
            continue
        dst = os.path.join(header_output_dir, profile)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"Copying CMSIS profile headers '{src}' -> '{dst}'")


def _find_arm_gnu_tool(tool_name):
    """
    Locate an arm-none-eabi-* binary under arduino_gcc_dir from generate_gsdk.cfg
    """
    if arduino_gcc_dir is None or not os.path.isdir(arduino_gcc_dir):
        return None
    # Prefer <arduino_gcc_dir>/<version>/bin/<tool>
    try:
        versions = sorted(
            (e for e in os.listdir(arduino_gcc_dir)
             if os.path.isdir(os.path.join(arduino_gcc_dir, e))),
            reverse=True,
        )
    except OSError:
        versions = []
    for version in versions:
        candidate = os.path.join(arduino_gcc_dir, version, "bin", tool_name)
        if os.path.isfile(candidate):
            return candidate
    # Also accept a direct bin/ under arduino_gcc_dir
    candidate = os.path.join(arduino_gcc_dir, "bin", tool_name)
    if os.path.isfile(candidate):
        return candidate
    return None


def _mutate_archive_member(archive_path, member, objcopy_args, work_suffix):
    """
    Extract one archive member, run objcopy on it, replace it in the archive.
    """
    ar_bin = _find_arm_gnu_tool("arm-none-eabi-ar")
    objcopy_bin = _find_arm_gnu_tool("arm-none-eabi-objcopy")
    if not ar_bin or not objcopy_bin or not os.path.exists(archive_path):
        print(f"Warning: cannot mutate {member} in {archive_path}")
        return False
    members = subprocess.check_output([ar_bin, "t", archive_path], text=True).splitlines()
    if member not in members:
        return False
    work_dir = archive_path + work_suffix
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.mkdir(work_dir)
    try:
        subprocess.check_call([ar_bin, "x", os.path.abspath(archive_path), member], cwd=work_dir)
        obj_path = os.path.join(work_dir, member)
        # infile == outfile keeps the edit in place (matches prior I2C redefine usage)
        subprocess.check_call([objcopy_bin] + list(objcopy_args) + [obj_path, obj_path])
        subprocess.check_call([ar_bin, "r", os.path.abspath(archive_path), member], cwd=work_dir)
        return True
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def weaken_matter_start_app_task_in_archive(archive_path):
    """
    Matter lighting-app AppTask::StartAppTask remains in gsdk.a (other AppTask
    symbols are needed). Arduino variants define a strong stub for setup()/loop();
    weaken the archive symbol so the variant wins at link time.
    """
    if _mutate_archive_member(
        archive_path,
        "AppTask.o",
        ["--weaken-symbol=_ZN7AppTask12StartAppTaskEv"],
        ".apptask_tmp",
    ):
        print(f"Weakened AppTask::StartAppTask in {archive_path}")
        return True
    return False


def rename_sl_i2c_irq_handlers_in_archive(archive_path):
    """
    SiSDK 2026 i2cspm depends on i2c_core (sl_i2c.c), which defines strong
    I2Cx_IRQHandler symbols that collide with Arduino Wire follower IRQs.
    Rename the SDK handlers so Wire can own the vector and forward in leader mode.
    """
    ar_bin = _find_arm_gnu_tool("arm-none-eabi-ar")
    nm_bin = _find_arm_gnu_tool("arm-none-eabi-nm")
    if not ar_bin or not os.path.exists(archive_path):
        print(f"Warning: cannot rename I2C IRQ handlers in {archive_path}")
        return False

    members = subprocess.check_output([ar_bin, "t", archive_path], text=True).splitlines()
    if "sl_i2c.o" not in members:
        return False

    # Skip if already renamed
    if nm_bin:
        nm_sl = subprocess.check_output([nm_bin, archive_path], text=True, stderr=subprocess.DEVNULL)
        in_sl_i2c = False
        has_renamed = False
        has_original = False
        for line in nm_sl.splitlines():
            if line.startswith("sl_i2c.o"):
                in_sl_i2c = True
                continue
            if in_sl_i2c and line.endswith(":") and "sl_i2c.o" not in line:
                in_sl_i2c = False
            if not in_sl_i2c:
                continue
            if "sl_i2c_I2C0_IRQHandler" in line or "sl_i2c_I2C1_IRQHandler" in line:
                has_renamed = True
            elif (" I2C0_IRQHandler" in line or " I2C1_IRQHandler" in line) and "sl_i2c_I2C" not in line:
                has_original = True
        if has_renamed and not has_original:
            print(f"I2C IRQ handlers already renamed in {archive_path}")
            return True

    redefine = [
        "--redefine-sym", "I2C0_IRQHandler=sl_i2c_I2C0_IRQHandler",
        "--redefine-sym", "I2C1_IRQHandler=sl_i2c_I2C1_IRQHandler",
        "--redefine-sym", "I2C2_IRQHandler=sl_i2c_I2C2_IRQHandler",
        "--redefine-sym", "I2C3_IRQHandler=sl_i2c_I2C3_IRQHandler",
    ]
    if _mutate_archive_member(archive_path, "sl_i2c.o", redefine, ".i2c_irq_tmp"):
        print(f"Renamed sl_i2c I2Cx_IRQHandler symbols in {archive_path}")
        return True
    return False


def copy_output_files_prebuild(output_dir, is_matter, is_ble_arduino, is_noradio, ai_capable, is_zigbee=False):
    """
    Get the built stuff in one place
    """
    print("Copying built files...")

    # Check if the archive has been created successfully
    prebuilt_core_archive_file = slc_output_dir + "gsdk.a"
    if not os.path.exists(prebuilt_core_archive_file):
        print("'gsdk.a' has not been created - build might've failed")
        exit(-1)

    # Avoids Wire vs sl_i2c I2Cx_IRQHandler multiple definition
    rename_sl_i2c_irq_handlers_in_archive(prebuilt_core_archive_file)

    # remove the output dir if it exists
    if os.path.exists(output_dir) and os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    os.mkdir(output_dir)

    # Get all the archive files from the project
    for (root, dirs, file) in os.walk(slc_output_dir):
        for f in file:
            filepath = os.path.join(root, f)
            if f.endswith(".a"):
                shutil.copy(filepath, output_dir)
                print(f"Copying '{f}'")

    # Get all the header files from the project
    if not is_matter and not is_zigbee:
        header_output_dir = output_dir + "include/"
        os.mkdir(header_output_dir)
        os.mkdir(header_output_dir + "psa")
        os.mkdir(header_output_dir + "mbedtls")
        os.mkdir(header_output_dir + "flatbuffers")
        os.mkdir(header_output_dir + "fixedpoint")
        os.mkdir(header_output_dir + "internal")
        count = 0
        for (root, dirs, file) in os.walk(slc_output_dir):
            for f in file:
                filepath = os.path.join(root, f)
                if f.endswith('.h'):
                    # Skip TFLite Micro headers (copied with structure below)
                    if ("tflite-micro/tensorflow" in filepath) or ("tflite_micro/tensorflow" in filepath):
                        print(f"Skipping '{f}' as it is in a tflite tensorflow tree")
                        continue
                    # Retain containing directory for 'psa' and 'mbedtls'
                    if "include/psa" in filepath:
                        shutil.copyfile(filepath, header_output_dir + "psa/" + str(f))
                    elif "include/mbedtls" in filepath:
                        shutil.copyfile(filepath, header_output_dir + "mbedtls/" + str(f))
                    elif "include/flatbuffers" in filepath:
                        shutil.copyfile(filepath, header_output_dir + "flatbuffers/" + str(f))
                    elif "gemmlowp/fixedpoint" in filepath:
                        shutil.copyfile(filepath, header_output_dir + "fixedpoint/" + str(f))
                    elif "gemmlowp/internal" in filepath:
                        shutil.copyfile(filepath, header_output_dir + "internal/" + str(f))
                    else:
                        shutil.copyfile(filepath, header_output_dir + str(f))
                    print(f"Copying '{filepath}'")
                    count += 1

        if ai_capable:
            # Copy the headers from tflite-micro with preserving the structure
            # AIML 2.x: third_party/tflite-micro/tensorflow
            # AIML 3.x: compiled_model/third_party/tflite_micro/tensorflow
            tflite_candidates = [
                slc_output_dir + "aiml_" + aiml_extension_version + "/compiled_model/third_party/tflite_micro/tensorflow",
                slc_output_dir + "aiml_" + aiml_extension_version + "/third_party/tflite-micro/tensorflow",
                slc_output_dir + "aiml_" + aiml_extension_version + "/third_party/tflite_micro/tensorflow",
            ]
            tflite_src = next((p for p in tflite_candidates if os.path.exists(p)), None)
            if tflite_src is None:
                print("Could not find tflite tensorflow headers under AIML extension")
                exit(-1)
            shutil.copytree(tflite_src, header_output_dir + "tensorflow")

        # Headers referenced by boards.txt (-imacros) but not always copied by -cpsdk
        copy_extra_sdk_headers(header_output_dir)

        # CMSIS 6.x uses nested includes like "m-profile/cmsis_gcc_m.h"
        copy_cmsis_profile_headers(slc_output_dir, header_output_dir)

        # Remove 'cc' files
        for (root, dirs, file) in os.walk(header_output_dir):
            for f in file:
                filepath = os.path.join(root, f)
                if f.endswith('.cc'):
                    os.remove(filepath)

        print(f"Copied {count} header files")

    # Copy the headers from a generated Zigbee variant while preserving the directory structure
    if is_zigbee:
        shutil.copytree(slc_output_dir + "autogen", output_dir + "autogen")
        shutil.copytree(slc_output_dir + "config", output_dir + "config")
        # Copy headers from the Simplicity SDK folder preserving directory structure
        sisdk_folder_path = slc_output_dir + "simplicity_sdk_" + gsdk_version
        sisdk_output_path = output_dir + "simplicity_sdk/"
        for (root, dirs, file) in os.walk(sisdk_folder_path):
            for f in file:
                filepath = os.path.join(root, f)
                if f.endswith('.h'):
                    rel_path = os.path.relpath(filepath, sisdk_folder_path)
                    dest_path = os.path.join(sisdk_output_path, rel_path)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copyfile(filepath, dest_path)
                    print(f"Copying '{rel_path}'")

        if ai_capable:
            # Copy AI/ML headers preserving structure
            aimlsdk_folder_path = slc_output_dir + "aiml_" + aiml_extension_version
            aiml_output_path = output_dir + "aiml/"
            for (root, dirs, file) in os.walk(aimlsdk_folder_path):
                for f in file:
                    filepath = os.path.join(root, f)
                    if f.endswith('.h'):
                        if "tflite-micro/tensorflow" in filepath:
                            continue
                        rel_path = os.path.relpath(filepath, aimlsdk_folder_path)
                        dest_path = os.path.join(aiml_output_path, rel_path)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copyfile(filepath, dest_path)
                        print(f"Copying AI/ML '{rel_path}'")
            # Copy tflite-micro headers with structure
            tflm_src = os.path.join(aimlsdk_folder_path, "third_party/tflite-micro/tensorflow")
            if os.path.exists(tflm_src):
                shutil.copytree(tflm_src, aiml_output_path + "third_party/tflite-micro/tensorflow")

        # SiSDK 2026.x: sl_gcc_preinclude.h lives under platform_core and is not always
        # pulled into the -cpsdk tree; Arduino -imacros needs it on the include path.
        toolchain_inc = os.path.join(
            output_dir, "simplicity_sdk", "platform_core", "platform", "common", "toolchain", "inc"
        )
        os.makedirs(toolchain_inc, exist_ok=True)
        preinclude_dst = os.path.join(toolchain_inc, "sl_gcc_preinclude.h")
        if not os.path.exists(preinclude_dst):
            for rel in (
                "platform_core/platform/common/toolchain/inc/sl_gcc_preinclude.h",
                "platform/common/toolchain/inc/sl_gcc_preinclude.h",
                "platform/common/toolchain/gcc/inc/sl_gcc_preinclude.h",
            ):
                src = os.path.join(gsdk_dir, rel)
                if os.path.exists(src):
                    shutil.copy(src, preinclude_dst)
                    print(f"Copying Zigbee toolchain header '{src}' -> '{preinclude_dst}'")
                    break
            else:
                print("Warning: sl_gcc_preinclude.h not found for Zigbee variant")

        # Remove source files from the copied directories
        for (root, dirs, file) in os.walk(output_dir):
            for f in file:
                filepath = os.path.join(root, f)
                if f.endswith('.c') or f.endswith('.cpp') or f.endswith('.cc') or f.endswith('.S'):
                    os.remove(filepath)

    # Copy the headers from a generated Matter variant while preserving the structure of the Matter SDK
    if is_matter:
        # Copy the whole output directory except for the SDK
        shutil.copytree(slc_output_dir + "autogen", output_dir + "autogen")
        shutil.copytree(slc_output_dir + "config", output_dir + "config")
        shutil.copytree(slc_output_dir + "matter_" + matter_extension_version, output_dir + "matter_" + matter_extension_version)
        shutil.copytree(slc_output_dir + "include", output_dir + "include")
        # Remove 'c' 'cpp' 'a' and 'S' files
        for (root, dirs, file) in os.walk(output_dir):
            for f in file:
                filepath = os.path.join(root, f)
                if f.endswith('.c'):
                    os.remove(filepath)
                if f.endswith('.cpp'):
                    os.remove(filepath)
                #if f.endswith('.a'):
                    #os.remove(filepath)
                if f.endswith('.S'):
                    os.remove(filepath)

        # Copy the headers from the Simplicity SDK folder
        header_output_dir = output_dir + "include/"
        # Create the folders for the structures we have to keep
        os.mkdir(header_output_dir + "openthread")
        os.mkdir(header_output_dir + "openthread/platform")
        os.mkdir(header_output_dir + "psa")
        os.mkdir(header_output_dir + "mbedtls")
        sisdk_folder_path = slc_output_dir + "simplicity_sdk_" + gsdk_version
        for (root, dirs, file) in os.walk(sisdk_folder_path):
            for f in file:
                filepath = os.path.join(root, f)
                if f.endswith('.h'):
                    filepath_norm = filepath.replace("\\", "/")
                    # ot-br-posix embeds a second OpenThread tree; skip it to avoid
                    # overwriting the canonical include/openthread headers.
                    if "ot-br-posix" in filepath_norm and "include/openthread" in filepath_norm:
                        continue
                    # Retain containing directory structure for the following
                    if "include/openthread/" in filepath_norm:
                        # Preserve provisional/ and other OT subdirs (flat basename
                        # copy used to overwrite link.h with provisional/link.h).
                        rel = filepath_norm.split("include/openthread/", 1)[1]
                        dest = os.path.join(header_output_dir, "openthread", rel)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copyfile(filepath, dest)
                    elif "include/psa" in filepath_norm:
                        shutil.copyfile(filepath, header_output_dir + "psa/" + str(f))
                    elif "include/mbedtls" in filepath_norm:
                        shutil.copyfile(filepath, header_output_dir + "mbedtls/" + str(f))
                    else:
                        dest = header_output_dir + str(f)
                        if not matter_should_copy_flat_header(filepath_norm, dest):
                            print(f"Skipping flat header conflict '{filepath}'")
                            continue
                        shutil.copyfile(filepath, dest)
                    print(f"Copying '{filepath}'")

        if ai_capable:
            # Create AI/ML specific include directories
            os.mkdir(header_output_dir + "flatbuffers")
            os.mkdir(header_output_dir + "fixedpoint")
            os.mkdir(header_output_dir + "internal")
            # Copy headers from the AI/ML SDK without preserving structure
            aimlsdk_folder_path = slc_output_dir + "aiml_" + aiml_extension_version
            for (root, dirs, file) in os.walk(aimlsdk_folder_path):
                for f in file:
                    filepath = os.path.join(root, f)
                    if f.endswith('.h'):
                        # Skip TFLite Micro headers (copied with structure below)
                        if ("tflite-micro/tensorflow" in filepath) or ("tflite_micro/tensorflow" in filepath):
                            print(f"Skipping '{f}' as it is in a tflite tensorflow tree")
                            continue
                        if "include/flatbuffers" in filepath:
                            shutil.copyfile(filepath, header_output_dir + "flatbuffers/" + str(f))
                        elif "gemmlowp/fixedpoint" in filepath:
                            shutil.copyfile(filepath, header_output_dir + "fixedpoint/" + str(f))
                        elif "gemmlowp/internal" in filepath:
                            shutil.copyfile(filepath, header_output_dir + "internal/" + str(f))
                        else:
                            shutil.copyfile(filepath, header_output_dir + str(f))
                        print(f"Copying '{filepath}'")
            # Copy the headers from tflite-micro with preserving the structure
            tflite_candidates = [
                slc_output_dir + "aiml_" + aiml_extension_version + "/compiled_model/third_party/tflite_micro/tensorflow",
                slc_output_dir + "aiml_" + aiml_extension_version + "/third_party/tflite-micro/tensorflow",
                slc_output_dir + "aiml_" + aiml_extension_version + "/third_party/tflite_micro/tensorflow",
            ]
            tflite_src = next((p for p in tflite_candidates if os.path.exists(p)), None)
            if tflite_src is None:
                print("Could not find tflite tensorflow headers under AIML extension")
                exit(-1)
            shutil.copytree(tflite_src, header_output_dir + "tensorflow")
            # Remove 'cc' files
            for (root, dirs, file) in os.walk(header_output_dir):
                for f in file:
                    filepath = os.path.join(root, f)
                    if f.endswith('.cc'):
                        os.remove(filepath)

        # -imacros sl_gcc_preinclude.h and CMSIS nested includes (same as non-Matter stacks)
        copy_extra_sdk_headers(header_output_dir)
        copy_cmsis_profile_headers(slc_output_dir, header_output_dir)

    # BLE (Arduino): HCI headers from SiSDK 2026.x bluetooth_le_controller
    if is_ble_arduino:
        ble_hci_headers = [
            (os.path.join(gsdk_dir, "bluetooth_le_controller", "inc"),
             ["sl_btctrl_hci_handler.h", "sl_btctrl_hci.h", "sl_hci_common_transport.h"]),
            (os.path.join(gsdk_dir, "bluetooth_le_controller", "utils", "hci_packet", "inc"),
             ["sl_btctrl_reset.h"]),
        ]
        copied = 0
        for header_dir, headers in ble_hci_headers:
            for header in headers:
                src_path = os.path.join(header_dir, header)
                if not os.path.exists(src_path):
                    print(f"Warning: missing BLE HCI header '{src_path}'")
                    continue
                shutil.copy(src_path, output_dir + "/include/")
                print(f"Copying '{header}' from {header_dir}")
                copied += 1
        # ArduinoBLE includes sl_btctrl_hci_reset.h; SiSDK renamed it to sl_btctrl_reset.h
        reset_hdr = os.path.join(output_dir, "include", "sl_btctrl_reset.h")
        reset_alias = os.path.join(output_dir, "include", "sl_btctrl_hci_reset.h")
        if os.path.exists(reset_hdr) and not os.path.exists(reset_alias):
            with open(reset_alias, "w") as f:
                f.write(
                    "/* ArduinoBLE expects this name; SiSDK provides sl_btctrl_reset.h */\n"
                    "#include \"sl_btctrl_reset.h\"\n"
                )
            print("Wrote ArduinoBLE alias header sl_btctrl_hci_reset.h")
            copied += 1
        # ArduinoBLE calls sl_bt_controller_init/deinit; wrappers live in arduino_ble_hci
        linklayer_hdr = os.path.join(output_dir, "include", "sl_btctrl_linklayer.h")
        if os.path.exists(linklayer_hdr):
            with open(linklayer_hdr, "r") as f:
                ll_text = f.read()
            if "sl_bt_controller_compat.h" not in ll_text:
                compat_block = (
                    "\n/* ArduinoBLE API names -> SiSDK sl_btctrl_* (arduino_ble_hci) */\n"
                    "#include \"sl_bt_controller_compat.h\"\n"
                )
                needle = '#include "sl_btctrl_linklayer_defs.h"'
                if needle in ll_text:
                    ll_text = ll_text.replace(needle, needle + compat_block, 1)
                else:
                    ll_text = ll_text + compat_block
                with open(linklayer_hdr, "w") as f:
                    f.write(ll_text)
                print("Patched sl_btctrl_linklayer.h with ArduinoBLE controller compat include")
                copied += 1
        print(f"Copied {copied} BLE HCI header file(s)")

    # Get the linkerfile
    shutil.copy(slc_output_dir + "autogen/linkerfile.ld", output_dir)

    print("Applying license to GSDK folder...")
    shutil.copy(gsdk_license_file, output_dir + "/LICENSE")


def copy_generated_sdk_to_variants(output_dir, variant_target_folder):
    """
    Copy the generated SDK to the variants folder (flat layout expected by boards.txt)
    """
    print("Copying generated SDK to variants folder...")

    print(f"Target folder: {variant_target_folder}")
    if os.path.exists(variant_target_folder):
        shutil.rmtree(variant_target_folder)

    shutil.copytree(output_dir, variant_target_folder)
    print("Finished copying to variants folder")

def cleanup(gsdk_soc_empty_folder, slcp_file_name, additional_files, keep_gen_folder=False):
    """
    Clean up after the copy-into-SDK generate flow (Matter / Zigbee).
    """
    # Remove the slcp file
    print("Cleaning up...")
    os.remove(gsdk_dir + gsdk_soc_empty_folder + slcp_file_name)
    for file in additional_files:
        # If the current element is a list - extract the filename and target directory and remove from there
        if type(file) == list:
            filename = os.path.basename(file[0])
            target_dir = file[1]
            os.remove(gsdk_dir + target_dir + filename)
        else:
            filename = os.path.basename(file)
            os.remove(gsdk_dir + gsdk_soc_empty_folder + filename)
    # Remove the generated project if requested
    if keep_gen_folder:
        print("Keeping the 'gen' folder")
    else:
        shutil.rmtree(slc_output_dir)


def cleanup_direct_generate(keep_gen_folder=False):
    """
    Clean up after direct package/ SLCP generation (nothing was copied into the SDK)
    """
    print("Cleaning up...")
    if keep_gen_folder:
        print("Keeping the 'gen' folder")
    else:
        if os.path.exists(slc_output_dir):
            shutil.rmtree(slc_output_dir)
    # Staged Matter workspace only holds symlinks + copied SLCP/ZAP; safe to drop
    workspace = os.path.abspath(matter_workspace_dir)
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
        print("Removed staged Matter workspace")


def get_platform_config_from_arguments():
    """
    Determines the platform configuration from the command line arguments
    """
    def print_available_configs():
        print("Available platform configurations:")
        for config in platform_configurations:
            print(config["name"])

    try:
        input_config_name = sys.argv[1]
    except Exception:
        print("Please provide a platform configuration name in the first argument!")
        print_available_configs()
        exit(-1)

    found = False
    for config in platform_configurations:
        if config["name"] == input_config_name:
            return config
    if not found:
        print(f"Platform configuration with the name '{input_config_name}' not found!")
        print_available_configs()
        exit(-1)


def get_keep_gen_folder_parameter_from_arguments():
    """
    Determines if the generated folder should be kept from the command line arguments
    """
    try:
        input_keep_gen_folder = sys.argv[2]
    except Exception:
        return False

    if input_keep_gen_folder == "--keep" or input_keep_gen_folder == "-k":
        return True
    else:
        return False

def read_config_file(config_file_path):
    with open(config_file_path, "r") as f:
        global gsdk_dir
        global slc_output_dir
        global gsdk_version
        global matter_extension_version
        global matter_extension_dir
        global aiml_extension_version
        global aiml_extension_dir
        global slc_cli
        global zap_cli
        global arduino_gcc_dir
        lines = f.readlines()
        for line in lines:
            if line.startswith("#") or len(line) < 3:
                continue
            config = line.split(" ")[0].strip()
            value = line.split(" ")[1].strip()
            if config == "gsdk_dir":
                gsdk_dir = value
            if config == "slc_output_dir":
                slc_output_dir = value
            if config == "gsdk_version":
                gsdk_version = value
            if config == "matter_extension_version":
                matter_extension_version = value
            if config == "matter_extension_dir":
                matter_extension_dir = value
            if config == "aiml_extension_version":
                aiml_extension_version = value
            if config == "aiml_extension_dir":
                aiml_extension_dir = value
            if config == "slc_cli":
                slc_cli = value
            if config == "zap_cli":
                zap_cli = value
            if config == "arduino_gcc_dir":
                arduino_gcc_dir = value
        if gsdk_dir is None or slc_output_dir is None or gsdk_version is None or matter_extension_version is None:
            print(f"Incomplete or incorrect config file ({config_file_path}), exiting...")
            exit(-1)
        if not os.path.exists(slc_cli):
            print(f"slc_cli path does not exist: {slc_cli}")
            exit(-1)
        if zap_cli is not None and not os.path.exists(zap_cli):
            print(f"zap_cli path does not exist: {zap_cli}")
            exit(-1)
        if arduino_gcc_dir is not None and not os.path.isdir(arduino_gcc_dir):
            print(f"arduino_gcc_dir path does not exist: {arduino_gcc_dir}")
            exit(-1)
        if matter_extension_dir is not None and not os.path.isdir(matter_extension_dir):
            print(f"matter_extension_dir path does not exist: {matter_extension_dir}")
            exit(-1)


# Configurations
all_platform_config = {
    "name": "all"
}

all_precomp_platform_config = {
    "name": "precomp_all"
}

noradio_precomp_all_platform_config = {
    "name": "noradio_precomp_all",
}

ble_arduino_precomp_all_platform_config = {
    "name": "ble_arduino_precomp_all",
}

ble_silabs_precomp_all_platform_config = {
    "name": "ble_silabs_precomp_all",
}

matter_precomp_all_platform_config = {
    "name": "matter_precomp_all",
}

zigbee_precomp_all_platform_config = {
    "name": "zigbee_precomp_all",
}

thingplusmatter_noradio_platform_config = {
    "name": "thingplusmatter_noradio",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_noradio.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h"]
}

thingplusmatter_noradio_prebuilt_platform_config = {
    "name": "thingplusmatter_noradio_precomp",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_noradio.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h"]
}

thingplusmatter_ble_arduino_platform_config = {
    "name": "thingplusmatter_ble_arduino",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_ble_arduino.slcp",
    "additional_files": []
}

thingplusmatter_ble_arduino_prebuilt_platform_config = {
    "name": "thingplusmatter_ble_arduino_precomp",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_ble_arduino.slcp",
    "additional_files": []
}

thingplusmatter_ble_silabs_platform_config = {
    "name": "thingplusmatter_ble_silabs",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_ble_silabs.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h"]
}

thingplusmatter_ble_silabs_prebuilt_platform_config = {
    "name": "thingplusmatter_ble_silabs_precomp",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_ble_silabs.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h"]
}

thingplusmatter_matter_platform_config = {
    "name": "thingplusmatter_matter",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_matter.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h",
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

thingplusmatter_matter_prebuilt_platform_config = {
    "name": "thingplusmatter_matter_precomp",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_matter.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h",
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

thingplusmatter_zigbee_platform_config = {
    "name": "thingplusmatter_zigbee",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_zigbee.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h"],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

thingplusmatter_zigbee_prebuilt_platform_config = {
    "name": "thingplusmatter_zigbee_precomp",
    "arduino_variant_name": "thingplusmatter",
    "board_opn": "brd2704a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/thingplusmatter/thingplusmatter_zigbee.slcp",
    "additional_files": ["slcp/thingplusmatter/sl_spidrv_eusart_thingplus1_config.h",
                         "slcp/thingplusmatter/sl_iostream_eusart_thingplus1_config.h"],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

xg27devkit_noradio_platform_config = {
    "name": "xg27devkit_noradio",
    "arduino_variant_name": "xg27devkit",
    "board_opn": "brd2602a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xg27devkit/xg27devkit_noradio.slcp",
    "additional_files": ["slcp/xg27devkit/sl_iostream_usart_xg27devkit1_config.h"]
}

xg27devkit_noradio_prebuilt_platform_config = {
    "name": "xg27devkit_noradio_precomp",
    "arduino_variant_name": "xg27devkit",
    "board_opn": "brd2602a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xg27devkit/xg27devkit_noradio.slcp",
    "additional_files": ["slcp/xg27devkit/sl_iostream_usart_xg27devkit1_config.h"]
}

xg27devkit_ble_arduino_platform_config = {
    "name": "xg27devkit_ble_arduino",
    "arduino_variant_name": "xg27devkit",
    "board_opn": "brd2602a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xg27devkit/xg27devkit_ble_arduino.slcp",
    "additional_files": []
}

xg27devkit_ble_arduino_prebuilt_platform_config = {
    "name": "xg27devkit_ble_arduino_precomp",
    "arduino_variant_name": "xg27devkit",
    "board_opn": "brd2602a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xg27devkit/xg27devkit_ble_arduino.slcp",
    "additional_files": []
}

xg27devkit_ble_silabs_platform_config = {
    "name": "xg27devkit_ble_silabs",
    "arduino_variant_name": "xg27devkit",
    "board_opn": "brd2602a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xg27devkit/xg27devkit_ble_silabs.slcp",
    "additional_files": ["slcp/xg27devkit/sl_iostream_usart_xg27devkit1_config.h"]
}

xg27devkit_ble_silabs_prebuilt_platform_config = {
    "name": "xg27devkit_ble_silabs_precomp",
    "arduino_variant_name": "xg27devkit",
    "board_opn": "brd2602a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xg27devkit/xg27devkit_ble_silabs.slcp",
    "additional_files": ["slcp/xg27devkit/sl_iostream_usart_xg27devkit1_config.h"]
}

xg24explorerkit_noradio_platform_config = {
    "name": "xg24explorerkit_noradio",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_noradio.slcp",
    "additional_files": []
}

xg24explorerkit_noradio_prebuilt_platform_config = {
    "name": "xg24explorerkit_noradio_precomp",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_noradio.slcp",
    "additional_files": []
}

xg24explorerkit_ble_arduino_platform_config = {
    "name": "xg24explorerkit_ble_arduino",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_ble_arduino.slcp",
    "additional_files": []
}

xg24explorerkit_ble_arduino_prebuilt_platform_config = {
    "name": "xg24explorerkit_ble_arduino_precomp",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_ble_arduino.slcp",
    "additional_files": []
}

xg24explorerkit_ble_silabs_platform_config = {
    "name": "xg24explorerkit_ble_silabs",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_ble_silabs.slcp",
    "additional_files": []
}

xg24explorerkit_ble_silabs_prebuilt_platform_config = {
    "name": "xg24explorerkit_ble_silabs_precomp",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_ble_silabs.slcp",
    "additional_files": []
}

xg24explorerkit_matter_platform_config = {
    "name": "xg24explorerkit_matter",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_matter.slcp",
    "additional_files": ["slcp/xg24explorerkit/sl_spidrv_eusart_xg24explorerkit1_config.h",
                         "slcp/xg24explorerkit/sl_iostream_eusart_xg24explorerkit1_config.h",
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

xg24explorerkit_matter_prebuilt_platform_config = {
    "name": "xg24explorerkit_matter_precomp",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_matter.slcp",
    "additional_files": ["slcp/xg24explorerkit/sl_spidrv_eusart_xg24explorerkit1_config.h",
                         "slcp/xg24explorerkit/sl_iostream_eusart_xg24explorerkit1_config.h",
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

xg24explorerkit_zigbee_platform_config = {
    "name": "xg24explorerkit_zigbee",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_zigbee.slcp",
    "additional_files": [],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

xg24explorerkit_zigbee_prebuilt_platform_config = {
    "name": "xg24explorerkit_zigbee_precomp",
    "arduino_variant_name": "xg24explorerkit",
    "board_opn": "brd2703a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/xg24explorerkit/xg24explorerkit_zigbee.slcp",
    "additional_files": [],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

xg24devkit_noradio_platform_config = {
    "name": "xg24devkit_noradio",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xg24devkit/xg24devkit_noradio.slcp",
    "additional_files": []
}

xg24devkit_noradio_prebuilt_platform_config = {
    "name": "xg24devkit_noradio_precomp",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xg24devkit/xg24devkit_noradio.slcp",
    "additional_files": []
}

xg24devkit_ble_arduino_platform_config = {
    "name": "xg24devkit_ble_arduino",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xg24devkit/xg24devkit_ble_arduino.slcp",
    "additional_files": []
}

xg24devkit_ble_arduino_prebuilt_platform_config = {
    "name": "xg24devkit_ble_arduino_precomp",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xg24devkit/xg24devkit_ble_arduino.slcp",
    "additional_files": []
}

xg24devkit_ble_silabs_platform_config = {
    "name": "xg24devkit_ble_silabs",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xg24devkit/xg24devkit_ble_silabs.slcp",
    "additional_files": []
}

xg24devkit_ble_silabs_prebuilt_platform_config = {
    "name": "xg24devkit_ble_silabs_precomp",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xg24devkit/xg24devkit_ble_silabs.slcp",
    "additional_files": []
}

xg24devkit_matter_platform_config = {
    "name": "xg24devkit_matter",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/xg24devkit/xg24devkit_matter.slcp",
    "additional_files": [["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

xg24devkit_matter_prebuilt_platform_config = {
    "name": "xg24devkit_matter_precomp",
    "arduino_variant_name": "xg24devkit",
    "board_opn": "brd2601b",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/xg24devkit/xg24devkit_matter.slcp",
    "additional_files": [["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

wio_mg24_noradio_platform_config = {
    "name": "wio_mg24_noradio",
    "arduino_variant_name": "wio_mg24",
    "board_opn": "brd2907a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/wio_mg24/wio_mg24_noradio.slcp",
    "additional_files": ["slcp/wio_mg24/sl_spidrv_eusart_wio_mg24_config.h",
                         "slcp/wio_mg24/sl_iostream_eusart_wio_mg24_config.h",
                         ["slcp/wio_mg24/brd2907a.slcc", "hardware/board/component/"],
                         ["slcp/wio_mg24/brd2907a_config.slcc", "hardware/board/config/component/"]]
}

wio_mg24_noradio_prebuilt_platform_config = {
    "name": "wio_mg24_noradio_precomp",
    "arduino_variant_name": "wio_mg24",
    "board_opn": "brd2907a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/wio_mg24/wio_mg24_noradio.slcp",
    "additional_files": ["slcp/wio_mg24/sl_spidrv_eusart_wio_mg24_config.h",
                         "slcp/wio_mg24/sl_iostream_eusart_wio_mg24_config.h",
                         ["slcp/wio_mg24/brd2907a.slcc", "hardware/board/component/"],
                         ["slcp/wio_mg24/brd2907a_config.slcc", "hardware/board/config/component/"]]
}

wio_mg24_ble_arduino_platform_config = {
    "name": "wio_mg24_ble_arduino",
    "arduino_variant_name": "wio_mg24",
    "board_opn": "brd2907a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/wio_mg24/wio_mg24_ble_arduino.slcp",
    "additional_files": []
}

wio_mg24_ble_arduino_prebuilt_platform_config = {
    "name": "wio_mg24_ble_arduino_precomp",
    "arduino_variant_name": "wio_mg24",
    "board_opn": "brd2907a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/wio_mg24/wio_mg24_ble_arduino.slcp",
    "additional_files": []
}

wio_mg24_ble_silabs_platform_config = {
    "name": "wio_mg24_ble_silabs",
    "arduino_variant_name": "wio_mg24",
    "board_opn": "brd2907a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/wio_mg24/wio_mg24_ble_silabs.slcp",
    "additional_files": ["slcp/wio_mg24/sl_spidrv_eusart_wio_mg24_config.h",
                         "slcp/wio_mg24/sl_iostream_eusart_wio_mg24_config.h",
                         ["slcp/wio_mg24/brd2907a.slcc", "hardware/board/component/"],
                         ["slcp/wio_mg24/brd2907a_config.slcc", "hardware/board/config/component/"]]
}

wio_mg24_ble_silabs_prebuilt_platform_config = {
    "name": "wio_mg24_ble_silabs_precomp",
    "arduino_variant_name": "wio_mg24",
    "board_opn": "brd2907a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/wio_mg24/wio_mg24_ble_silabs.slcp",
    "additional_files": ["slcp/wio_mg24/sl_spidrv_eusart_wio_mg24_config.h",
                         "slcp/wio_mg24/sl_iostream_eusart_wio_mg24_config.h",
                         ["slcp/wio_mg24/brd2907a.slcc", "hardware/board/component/"],
                         ["slcp/wio_mg24/brd2907a_config.slcc", "hardware/board/config/component/"]]
}

bgm220explorerkit_noradio_platform_config = {
    "name": "bgm220explorerkit_noradio",
    "arduino_variant_name": "bgm220explorerkit",
    "board_opn": "brd4314a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/bgm220explorerkit/bgm220explorerkit_noradio.slcp",
    "additional_files": []
}

bgm220explorerkit_noradio_prebuilt_platform_config = {
    "name": "bgm220explorerkit_noradio_precomp",
    "arduino_variant_name": "bgm220explorerkit",
    "board_opn": "brd4314a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/bgm220explorerkit/bgm220explorerkit_noradio.slcp",
    "additional_files": []
}

bgm220explorerkit_ble_arduino_platform_config = {
    "name": "bgm220explorerkit_ble_arduino",
    "arduino_variant_name": "bgm220explorerkit",
    "board_opn": "brd4314a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/bgm220explorerkit/bgm220explorerkit_ble_arduino.slcp",
    "additional_files": []
}

bgm220explorerkit_ble_arduino_prebuilt_platform_config = {
    "name": "bgm220explorerkit_ble_arduino_precomp",
    "arduino_variant_name": "bgm220explorerkit",
    "board_opn": "brd4314a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/bgm220explorerkit/bgm220explorerkit_ble_arduino.slcp",
    "additional_files": []
}

bgm220explorerkit_ble_silabs_platform_config = {
    "name": "bgm220explorerkit_ble_silabs",
    "arduino_variant_name": "bgm220explorerkit",
    "board_opn": "brd4314a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/bgm220explorerkit/bgm220explorerkit_ble_silabs.slcp",
    "additional_files": []
}

bgm220explorerkit_ble_silabs_prebuilt_platform_config = {
    "name": "bgm220explorerkit_ble_silabs_precomp",
    "arduino_variant_name": "bgm220explorerkit",
    "board_opn": "brd4314a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/bgm220explorerkit/bgm220explorerkit_ble_silabs.slcp",
    "additional_files": []
}

nanomatter_noradio_platform_config = {
    "name": "nano_matter_noradio",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/nano_matter/nano_matter_noradio.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"]]
}

nanomatter_noradio_prebuilt_platform_config = {
    "name": "nano_matter_noradio_precomp",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/nano_matter/nano_matter_noradio.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"]]
}

nanomatter_ble_arduino_platform_config = {
    "name": "nano_matter_ble_arduino",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/nano_matter/nano_matter_ble_arduino.slcp",
    "additional_files": []
}

nanomatter_ble_arduino_prebuilt_platform_config = {
    "name": "nano_matter_ble_arduino_precomp",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/nano_matter/nano_matter_ble_arduino.slcp",
    "additional_files": []
}

nanomatter_ble_silabs_platform_config = {
    "name": "nano_matter_ble_silabs",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/nano_matter/nano_matter_ble_silabs.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"]]
}

nanomatter_ble_silabs_prebuilt_platform_config = {
    "name": "nano_matter_ble_silabs_precomp",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/nano_matter/nano_matter_ble_silabs.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"]]
}

nanomatter_matter_platform_config = {
    "name": "nano_matter_matter",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/nano_matter/nano_matter_matter.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"],
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Arduino",
    "matter_vendor_id": "0x1515"
}

nanomatter_matter_prebuilt_platform_config = {
    "name": "nano_matter_matter_precomp",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/nano_matter/nano_matter_matter.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"],
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Arduino",
    "matter_vendor_id": "0x1515"
}

nanomatter_zigbee_platform_config = {
    "name": "nano_matter_zigbee",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/nano_matter/nano_matter_zigbee.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"]],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

nanomatter_zigbee_prebuilt_platform_config = {
    "name": "nano_matter_zigbee_precomp",
    "arduino_variant_name": "nano_matter",
    "board_opn": "brd2707a",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/nano_matter/nano_matter_zigbee.slcp",
    "additional_files": ["slcp/nano_matter/sl_spidrv_eusart_nanomatter_config.h",
                         "slcp/nano_matter/sl_spidrv_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_iostream_usart_nanomatter_config.h",
                         "slcp/nano_matter/sl_iostream_eusart_nanomatter1_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter_config.h",
                         "slcp/nano_matter/sl_i2cspm_nanomatter1_config.h",
                         ["slcp/nano_matter/brd2707a.slcc", "hardware/board/component/"],
                         ["slcp/nano_matter/brd2707a_config.slcc", "hardware/board/config/component/"]],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

lyra24p20_noradio_platform_config = {
    "name": "lyra24p20_noradio",
    "arduino_variant_name": "lyra24p20",
    "board_opn": "brd2904a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/lyra24p20/lyra24p20_noradio.slcp",
    "additional_files": ["slcp/lyra24p20/sl_spidrv_eusart_lyra24p20_config.h",
                         "slcp/lyra24p20/sl_iostream_eusart_lyra24p20_config.h"]
}

lyra24p20_noradio_prebuilt_platform_config = {
    "name": "lyra24p20_noradio_precomp",
    "arduino_variant_name": "lyra24p20",
    "board_opn": "brd2904a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/lyra24p20/lyra24p20_noradio.slcp",
    "additional_files": ["slcp/lyra24p20/sl_spidrv_eusart_lyra24p20_config.h",
                         "slcp/lyra24p20/sl_iostream_eusart_lyra24p20_config.h"]
}

lyra24p20_ble_arduino_platform_config = {
    "name": "lyra24p20_ble_arduino",
    "arduino_variant_name": "lyra24p20",
    "board_opn": "brd2904a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/lyra24p20/lyra24p20_ble_arduino.slcp",
    "additional_files": []
}

lyra24p20_ble_arduino_prebuilt_platform_config = {
    "name": "lyra24p20_ble_arduino_precomp",
    "arduino_variant_name": "lyra24p20",
    "board_opn": "brd2904a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/lyra24p20/lyra24p20_ble_arduino.slcp",
    "additional_files": []
}

lyra24p20_ble_silabs_platform_config = {
    "name": "lyra24p20_ble_silabs",
    "arduino_variant_name": "lyra24p20",
    "board_opn": "brd2904a",
    "ai_capable": False,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/lyra24p20/lyra24p20_ble_silabs.slcp",
    "additional_files": ["slcp/lyra24p20/sl_spidrv_eusart_lyra24p20_config.h",
                         "slcp/lyra24p20/sl_iostream_eusart_lyra24p20_config.h"]
}

lyra24p20_ble_silabs_prebuilt_platform_config = {
    "name": "lyra24p20_ble_silabs_precomp",
    "arduino_variant_name": "lyra24p20",
    "board_opn": "brd2904a",
    "ai_capable": False,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/lyra24p20/lyra24p20_ble_silabs.slcp",
    "additional_files": ["slcp/lyra24p20/sl_spidrv_eusart_lyra24p20_config.h",
                         "slcp/lyra24p20/sl_iostream_eusart_lyra24p20_config.h"]
}

xiao_mg24_noradio_platform_config = {
    "name": "xiao_mg24_noradio",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_noradio.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h"]
}

xiao_mg24_noradio_prebuilt_platform_config = {
    "name": "xiao_mg24_noradio_precomp",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'noradio',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_noradio.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h"]
}

xiao_mg24_ble_arduino_platform_config = {
    "name": "xiao_mg24_ble_arduino",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_ble_arduino.slcp",
    "additional_files": []
}

xiao_mg24_ble_arduino_prebuilt_platform_config = {
    "name": "xiao_mg24_ble_arduino_precomp",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_arduino',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_ble_arduino.slcp",
    "additional_files": []
}

xiao_mg24_ble_silabs_platform_config = {
    "name": "xiao_mg24_ble_silabs",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_ble_silabs.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h"]
}

xiao_mg24_ble_silabs_prebuilt_platform_config = {
    "name": "xiao_mg24_ble_silabs_precomp",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'ble_silabs',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_ble_silabs.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h"]
}

xiao_mg24_matter_platform_config = {
    "name": "xiao_mg24_matter",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_matter.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h",
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

xiao_mg24_matter_prebuilt_platform_config = {
    "name": "xiao_mg24_matter_precomp",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'matter',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_matter.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h",
                         ["slcp/common/MatterBLE.h", "extension/matter_extension/third_party/matter_sdk/examples/lighting-app/silabs/include/"]],
    "matter_zap_file": "slcp/common/arduino_matter.zap",
    "matter_vendor_name": "Silicon Labs",
    "matter_vendor_id": "0x1049"
}

xiao_mg24_zigbee_platform_config = {
    "name": "xiao_mg24_zigbee",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": False,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_zigbee.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h"],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

xiao_mg24_zigbee_prebuilt_platform_config = {
    "name": "xiao_mg24_zigbee_precomp",
    "arduino_variant_name": "xiao_mg24",
    "board_opn": "brd4187c",
    "ai_capable": True,
    "prebuild": True,
    "protocol_stack": 'zigbee',
    "slcp_file": "slcp/xiao_mg24/xiao_mg24_zigbee.slcp",
    "additional_files": ["slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_spidrv_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_iostream_usart_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_iostream_eusart_xiao_mg24_1_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_config.h",
                         "slcp/xiao_mg24/sl_i2cspm_xiao_mg24_1_config.h"],
    "zigbee_zap_file": "slcp/common/arduino_zigbee.zap"
}

platform_configurations = [all_platform_config,
                           all_precomp_platform_config,
                           noradio_precomp_all_platform_config,
                           ble_arduino_precomp_all_platform_config,
                           ble_silabs_precomp_all_platform_config,
                           matter_precomp_all_platform_config,
                           zigbee_precomp_all_platform_config,
                           thingplusmatter_noradio_platform_config,
                           thingplusmatter_noradio_prebuilt_platform_config,
                           thingplusmatter_ble_arduino_platform_config,
                           thingplusmatter_ble_arduino_prebuilt_platform_config,
                           thingplusmatter_ble_silabs_platform_config,
                           thingplusmatter_ble_silabs_prebuilt_platform_config,
                           thingplusmatter_matter_platform_config,
                           thingplusmatter_matter_prebuilt_platform_config,
                           thingplusmatter_zigbee_platform_config,
                           thingplusmatter_zigbee_prebuilt_platform_config,
                           xg27devkit_noradio_platform_config,
                           xg27devkit_noradio_prebuilt_platform_config,
                           xg27devkit_ble_arduino_platform_config,
                           xg27devkit_ble_arduino_prebuilt_platform_config,
                           xg27devkit_ble_silabs_platform_config,
                           xg27devkit_ble_silabs_prebuilt_platform_config,
                           xg24explorerkit_noradio_platform_config,
                           xg24explorerkit_noradio_prebuilt_platform_config,
                           xg24explorerkit_ble_arduino_platform_config,
                           xg24explorerkit_ble_arduino_prebuilt_platform_config,
                           xg24explorerkit_ble_silabs_platform_config,
                           xg24explorerkit_ble_silabs_prebuilt_platform_config,
                           xg24explorerkit_matter_platform_config,
                           xg24explorerkit_matter_prebuilt_platform_config,
                           xg24explorerkit_zigbee_platform_config,
                           xg24explorerkit_zigbee_prebuilt_platform_config,
                           xg24devkit_noradio_platform_config,
                           xg24devkit_noradio_prebuilt_platform_config,
                           xg24devkit_ble_arduino_platform_config,
                           xg24devkit_ble_arduino_prebuilt_platform_config,
                           xg24devkit_ble_silabs_platform_config,
                           xg24devkit_ble_silabs_prebuilt_platform_config,
                           xg24devkit_matter_platform_config,
                           xg24devkit_matter_prebuilt_platform_config,
                           #wio_mg24_noradio_platform_config,
                           #wio_mg24_noradio_prebuilt_platform_config,
                           #wio_mg24_ble_arduino_platform_config,
                           #wio_mg24_ble_arduino_prebuilt_platform_config,
                           bgm220explorerkit_noradio_platform_config,
                           bgm220explorerkit_noradio_prebuilt_platform_config,
                           bgm220explorerkit_ble_arduino_platform_config,
                           bgm220explorerkit_ble_arduino_prebuilt_platform_config,
                           bgm220explorerkit_ble_silabs_platform_config,
                           bgm220explorerkit_ble_silabs_prebuilt_platform_config,
                           nanomatter_noradio_platform_config,
                           nanomatter_noradio_prebuilt_platform_config,
                           nanomatter_ble_arduino_platform_config,
                           nanomatter_ble_arduino_prebuilt_platform_config,
                           nanomatter_ble_silabs_platform_config,
                           nanomatter_ble_silabs_prebuilt_platform_config,
                           nanomatter_matter_platform_config,
                           nanomatter_matter_prebuilt_platform_config,
                           nanomatter_zigbee_platform_config,
                           nanomatter_zigbee_prebuilt_platform_config,
                           lyra24p20_noradio_platform_config,
                           lyra24p20_noradio_prebuilt_platform_config,
                           lyra24p20_ble_arduino_platform_config,
                           lyra24p20_ble_arduino_prebuilt_platform_config,
                           lyra24p20_ble_silabs_platform_config,
                           lyra24p20_ble_silabs_prebuilt_platform_config,
                           xiao_mg24_noradio_platform_config,
                           xiao_mg24_noradio_prebuilt_platform_config,
                           xiao_mg24_ble_arduino_platform_config,
                           xiao_mg24_ble_arduino_prebuilt_platform_config,
                           xiao_mg24_ble_silabs_platform_config,
                           xiao_mg24_ble_silabs_prebuilt_platform_config,
                           xiao_mg24_matter_platform_config,
                           xiao_mg24_matter_prebuilt_platform_config,
                           xiao_mg24_zigbee_platform_config,
                           xiao_mg24_zigbee_prebuilt_platform_config]


if __name__ == "__main__":
    main()
