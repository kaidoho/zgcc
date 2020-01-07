import sys
import os
from subprocess import *
import glob
import json
import logging
import shutil
import threading
from time import sleep
import urllib.request
import tarfile
import pathlib


logfile = os.getcwd() + "/log.txt"

if os.path.isfile(logfile):
    os.remove(logfile)

logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s",datefmt='%Y-%m-%d %H:%M:%S')
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
fileHandler = logging.FileHandler("{0}".format(logfile))
fileHandler.setFormatter(logFormatter)
rootLogger.addHandler(fileHandler)

rootLogger.addHandler(consoleHandler)
logger = logging.getLogger()

gBuildStep = 0

def log_build_step(text):
    global gBuildStep
    gBuildStep = gBuildStep +1
    logger.info("============================================")
    logger.info("==")
    logger.info("== Step {0}) {1}".format(str(gBuildStep), text))
    logger.info("==")
    logger.info("============================================")



def download_archive(dldir, pkg):
    fname = pkg['name'] + "-" + pkg['version'] + "." +  pkg['suffix']
    url = pkg['origin'] + "/" + fname
    dest = dldir + "/" +fname
    if os.path.isfile(dest):
        logger.info("Skipping download of: {0} - file already exists".format(url))
    else:
        logger.info("Downloading: {0}".format(url))
        urllib.request.urlretrieve(url, dest)




def download_source_archives(dl_dir,pkg_spec):
    log_build_step("Download source archives")

    if False == os.path.exists(dl_dir):
        os.mkdir(dl_dir)

    for pkg in pkg_spec['packages']:
        download_archive(dl_dir, pkg)


def run_cmd_env(cmd, workdir,cmd_env ):

  logger.warning("Building with {0}".format(cmd))
  p = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True, bufsize=1,  cwd=workdir, env=cmd_env)

  for line in iter(p.stdout.readline, b''):
    tmp = str(line)
    if tmp.endswith("\\r\\n'"):
      logger.info(tmp[2:len(tmp)-5])
    elif tmp.endswith("\\r\\n\""):
      logger.info(tmp[2:len(tmp)-5])
    else:
      logger.info(tmp[2:len(tmp)-3])
  p.stdout.close()
  p.wait()



def patch_source_folder(dest_dir,patch_dir):
    env = os.environ.copy()
    for patch in pathlib.Path(patch_dir).glob("*.patch"):
        cmd = "patch -p1 < {0}".format(patch)
        run_cmd_env(cmd, dest_dir, env)


def extract_package(dl_dir, dest_dir,patch_dir, pkg):
    fname = pkg['name'] + "-" + pkg['version'] + "." + pkg['suffix']
    dl_dir_help = dest_dir + "/"+pkg['name'] + "-" + pkg['version']
    patch_dir_help = patch_dir + "/" + pkg['name'] + "-" + pkg['version']

    if False == os.path.exists(dl_dir_help):
        logger.info("Extract package: {0}".format(fname))
        f = tarfile.open(dl_dir + "/" + fname)
        f.extractall(path=dest_dir)
        f.close()
        patch_source_folder(dl_dir_help,patch_dir_help)
    else:
        logger.info("Skip extraction of package: {0} - already extracted".format(fname))




def extract_source_archives(dl_dir, source_dir, patch_dir, pkg_spec):
    log_build_step("Extract source archives")

    if False == os.path.exists(source_dir):
        os.mkdir(source_dir)

    for pkg in pkg_spec['packages']:
        local_source_dir = source_dir + "/stage"+ pkg['stage']
        if False == os.path.exists(local_source_dir):
            os.mkdir(local_source_dir)

        extract_package(dl_dir, local_source_dir,patch_dir,pkg)


def read_package_spec():
    if os.path.isfile('packages.json'):
        with open('packages.json', 'r') as f:
             return json.load(f)
    else:
        logger.error("Can't find package specification")
        exit(-1)


def get_source_dir(top ,pkg):
    return top + "/stage"+ pkg['stage'] + "/" + pkg['name'] + "-" + pkg['version']


def get_install_dir(top ,pkg):

    if pkg['stage'] == "0":
        return top + "/stage"+ pkg['stage'] + "/" + pkg['name'] + "-" + pkg['version']

    return top + "/stage"+ pkg['stage']

def get_package_spec(name , pkg_spec):
    idx = name.find('-')

    if idx != -1:
        name = name[:idx]

    for pkg in pkg_spec['packages']:
        if pkg["name"] == name:
            return pkg

def guess_host_triplet(src_dir,pkg_spec):
    log_build_step("Identify host triplet")
    cmd = ["./config.guess"]
    pkg=get_package_spec("binutils", pkg_spec)
    workdir = src_dir + "/stage" + pkg['stage'] + "/" + pkg['name'] + "-" + pkg['version']

    p = Popen(cmd, stdout=PIPE, stderr=STDOUT, bufsize=1, cwd=workdir)
    for line in iter(p.stdout.readline, b''):
        tmp = str(line)
        if tmp.endswith("\\r\\n'"):
            tmp = tmp[2:len(tmp) - 5]
        elif tmp.endswith("\\r\\n\""):
            tmp = tmp[2:len(tmp) - 5]
        else:
            tmp = tmp[2:len(tmp) - 3]

    p.stdout.close()
    p.wait()
    logger.info("Host is: {0}".format(tmp))

    return tmp


def build_and_install(cfgcmd,makecmd,makeinstallcmd,  source_dir, env):
    run_cmd_env(cfgcmd, source_dir, env)
    run_cmd_env(makecmd, source_dir, env)
    run_cmd_env(makeinstallcmd, source_dir, env)


def get_package_make_cmd(name):
    if name == "gcc-stage-1":
        cmd = "make -j{0} all-gcc".format(len(os.sched_getaffinity(0)))
    else:
        cmd = "make -j{0}".format(len(os.sched_getaffinity(0)))
    return cmd

def get_package_make_install_cmd(name):
    if name == "gcc-stage-1":
        cmd = "make install-gcc"
    else:
        cmd = "make install"
    return cmd


def get_package_build_config(name, top_install_dir, pkg_install_dir, build_triplet, host_triplet,target_triplet, pkg_spec):
    install_dir_gmp = get_install_dir(top_install_dir, get_package_spec("gmp", pkg_spec))
    install_dir_mpfr = get_install_dir(top_install_dir, get_package_spec("mpfr", pkg_spec))
    install_dir_mpc = get_install_dir(top_install_dir, get_package_spec("mpc", pkg_spec))
    install_dir_isl = get_install_dir(top_install_dir, get_package_spec("isl", pkg_spec))
    if name == "zlib":
        cmd = "./configure \
                --static \
                --prefix={0}".format(pkg_install_dir)

    elif name == "gmp":
        cmd = "./configure \
        --build={0} \
        --host={1} \
        --prefix={2} \
        --enable-cxx \
        --disable-shared".format(
        build_triplet,host_triplet,pkg_install_dir)
    elif name == "mpfr":
        cmd =   "./configure \
        --build={0} \
        --host={1} \
        --prefix={2} \
        --disable-shared \
        --with-gmp={3}".format(
            build_triplet, host_triplet, pkg_install_dir, install_dir_gmp)
    elif name == "mpc":
        cmd =   "./configure \
        --build={0} \
        --host={1} \
        --prefix={2} \
        --disable-shared \
        --with-gmp={3} \
        --with-mpfr={4}".format(
            build_triplet,
            host_triplet,
            pkg_install_dir,
            install_dir_gmp,
            install_dir_mpfr)
    elif name == "isl":
        cmd =   "./configure \
        --build={0} \
        --host={1} \
        --prefix={2} \
        --disable-shared \
        --with-gmp-prefix={3}".format(
            build_triplet,
            host_triplet,
            pkg_install_dir,
            install_dir_gmp)
    elif name == "expat":
        cmd = "./configure \
        --build={0} \
        --host={1} \
        --prefix={2} \
        --disable-shared".format(
        build_triplet,host_triplet,pkg_install_dir)
    elif name == "binutils":
        cmd = "./configure \
            --target={0} \
            --prefix={1} \
            --disable-nls \
            --enable-interwork \
            --enable-multilib \
            --enable-plugins \
            --with-gmp={2}\
            --with-mpc={3}\
            --with-mpfr={4}\
            --with-isl={5}\
            --with-system-zlib".format(
            target_triplet,
            pkg_install_dir,
            install_dir_gmp,
            install_dir_mpc,
            install_dir_mpfr,
            install_dir_isl)
    elif name == "gcc-stage-1":
        cmd = "./configure \
            --target={0} \
            --prefix={1} \
            --libexecdir={1}/lib \
            --disable-decimal-float \
            --disable-libffi \
            --disable-libgomp \
            --disable-libmudflap \
            --disable-libquadmath \
            --disable-libssp \
            --disable-libstdcxx-pch \
            --disable-nls \
            --disable-shared \
            --enable-threads=zephyr\
            --disable-tls \
            --enable-languages=c\
            --without-headers\
            --with-newlib \
        	--with-gnu-as \
        	--with-gnu-ld \
            --with-sysroot={1}/{0} \
            --with-gmp={2} \
            --with-mpc={3}\
            --with-mpfr={4}\
            --with-isl={5}\
            --with-system-zlib".format(
            target_triplet,
            pkg_install_dir,
            install_dir_gmp,
            install_dir_mpc,
            install_dir_mpfr,
            install_dir_isl)
    elif name == "newlib":
        cmd = "./configure \
            --target={0} \
            --disable-newlib-supplied-syscalls \
            --enable-newlib-reent-small \
            --disable-newlib-fvwrite-in-streamio \
            --disable-newlib-fseek-optimization \
            --disable-newlib-wide-orient \
            --disable-newlib-unbuf-stream-opt \
            --enable-newlib-global-atexit \
            --enable-newlib-retargetable-locking \
            --enable-newlib-global-stdio-streams \
            --disable-nls".format(target_triplet)


    return cmd

def get_build_env(name,top_install_dir, pkg_spec):
    env = os.environ.copy()
    install_dir_zlib = get_install_dir(top_install_dir, get_package_spec("zlib", pkg_spec))

    if (name == "binutils") or (name == "gcc-stage-1"):
        cppflags = "-I{0}/include".format(install_dir_zlib)
        ldflags = "-L{0}/lib".format(install_dir_zlib)
        env["CPPFLAGS"] = cppflags
        env["LDFLAGS"] = ldflags
    elif (name == "newlib") or (name == "gcc-stage-2"):
        cppflags = "-I{0}/include".format(install_dir_zlib)
        ldflags = "-L{0}/lib".format(install_dir_zlib)
        install_dir_gcc = get_install_dir(top_install_dir, get_package_spec("gcc", pkg_spec))+ "/bin"
        logger.warning("GCC Install Dir: {0}".format(install_dir_gcc))
        env["CPPFLAGS"] = cppflags
        env["LDFLAGS"] = ldflags
        env["PATH"] += os.pathsep + install_dir_gcc

    return env



def build_package(name, top_source_dir, top_install_dir , build_triplet, host_triplet,target_triplet,pkg_spec):
    bpkg = get_package_spec(name, pkg_spec)
    bsource_dir = get_source_dir(top_source_dir, bpkg)
    binstall_dir = get_install_dir(top_install_dir, bpkg)

    env = get_build_env(name,top_install_dir, pkg_spec)

    cfgcmd = get_package_build_config(name, top_install_dir, binstall_dir, build_triplet,
                                   host_triplet,target_triplet, pkg_spec)
    makecmd = get_package_make_cmd(name)
    makeinstallcmd = get_package_make_install_cmd(name)
    build_and_install(cfgcmd,makecmd,makeinstallcmd, bsource_dir, env)



def build_stage0(source_dir, install_dir ,host_triplet,target_triplet,pkg_spec):
    log_build_step("Build host toolchain")
    bpacks = {
        "zlib" : 1,
        "gmp" : 1,
        "mpfr": 1,
        "mpc": 1,
        "isl": 1,
        "expat": 1}

    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    for name, build in bpacks.items():
        if build == 1:
            build_package(name,source_dir, install_dir , host_triplet, host_triplet, target_triplet, pkg_spec)

def build_stage1(source_dir, install_dir, host_triplet, target_triplet, pkg_spec):
    log_build_step("Build host toolchain")
    bpacks = {
        "binutils": 1,
        "gcc-stage-1": 1}

    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    for name, build in bpacks.items():
        if build == 1:
            build_package(name, source_dir, install_dir, host_triplet, host_triplet, target_triplet,
                          pkg_spec)


def build_stage2(source_dir, install_dir, host_triplet, target_triplet, pkg_spec):
    log_build_step("Build stage 2")
    bpacks = {
        "newlib" : 1,
        "gcc-stage-2": 0}

    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    for name, build in bpacks.items():
        if build == 1:
            build_package(name,source_dir, install_dir , host_triplet, host_triplet, target_triplet, pkg_spec)




if __name__ == '__main__':

    target_triplet = "arm-none-zephyr2"
    pkg_spec = read_package_spec()
    dl_dir = os.getcwd() + "/archives"
    source_dir = os.getcwd() + "/source"
    install_dir = os.getcwd() + "/install"
    stage0_install_dir =install_dir + "/stage0"
    stage1_install_dir = install_dir + "/stage1"
    patch_dir = os.getcwd() + "/patches"

    stage2_install_dir = install_dir + "/stage2"


    download_source_archives(dl_dir,pkg_spec)
    extract_source_archives(dl_dir, source_dir, patch_dir, pkg_spec)

    host_triplet = guess_host_triplet(source_dir,pkg_spec)

    #build_stage0(source_dir, install_dir ,host_triplet, target_triplet ,pkg_spec)
    #build_stage1(source_dir, install_dir, host_triplet, target_triplet, pkg_spec)
    build_stage2(source_dir, install_dir, host_triplet, target_triplet, pkg_spec)


    #build_toolchain_stage2(source_dir, stage2_install_dir ,host_triplet, target_triplet ,pkg_spec)

