#!/usr/bin/env bash
#SBATCH --job-name=simdog-distECM-0p5c
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=01:30:00
#SBATCH --partition=cn_768_917
#SBATCH --output=slurm.%j.out
#SBATCH --error=slurm.%j.err

set -euo pipefail
workdir="${SLURM_SUBMIT_DIR:?missing Slurm submit directory}"
cd "$workdir"
remote_user_home="$(getent passwd "$(id -un)" | cut -d: -f6)"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
source "$remote_user_home/yeesuan/envs/comsol64_env.sh"
comsol_bin="$remote_user_home/yeesuan/apps/comsol64/multiphysics/bin/comsol"

cp distributedECMOriginal.java DistributedECMdebug.java
"$comsol_bin" compile DistributedECMdebug.java
"$comsol_bin" compile DistributedECMFixed.java
test -s DistributedECMFixed.class

prefix="fixed_0p5c_10s"
"$comsol_bin" batch \
  -inputfile "$workdir/DistributedECMFixed.class" \
  -nosave \
  -batchlog "${prefix}_comsol.log" \
  -prodargs \
    "prefix=$prefix" \
    branch=signed \
    constraint=weak \
    C_rate=0.5 \
    ramp_time=1[s] \
    t_final=10[s] \
    dt_out=0.1[s] \
    max_step=0.02[s]

test -s "${prefix}_built.mph"
test -s "${prefix}_solved.mph"
test -s "${prefix}_global.csv"
! grep -Eiq 'Error|Exception|Failed to|Singular matrix|Repeated error test' "${prefix}_comsol.log"
python3 validate_smoke.py "${prefix}_global.csv" --expected-final 10 \
  > "${prefix}_validation.txt"
sha256sum \
  distributedECMOriginal.java DistributedECMFixed.java \
  "${prefix}_built.mph" "${prefix}_solved.mph" "${prefix}_global.csv" \
  "${prefix}_validation.txt" > "${prefix}_manifest.sha256"
