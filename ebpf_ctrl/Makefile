# Actual location of the makefile
ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# Argument for the CLANG compiler
LLC ?= llc
CLANG ?= clang
override INCLUDES+=-I./libbpf/include/
override LIBS+=
# Optimization flags to save space
override CFLAGS+= -O2 -g -D__KERNEL__ -D__ASM_SYSREG_H \
		-Wno-unused-value  -Wno-pointer-sign \
		-Wno-compare-distinct-pointer-types \
		-Wno-gnu-variable-sized-type-not-at-end \
		-Wno-address-of-packed-member -Wno-tautological-compare \
		-Wno-unknown-warning-option -Wnoparentheses-equality \
		-Wextra -Wall -Wshadow -Wpointer-arith -Wcast-qual \
		-std=gnu11 # -pedantic

# If needed, bpf target files can be hardcoded here
# This can be any file of type ".c", ".bc" or, ".o"
BPFOBJ=hbm_out_kern.o
# Get the source name of the object to match targets
BPFNAME=$(basename $(BPFOBJ))

all: verify_target_bpf $(BPFOBJ) ebpf_rate_control

# Verify LLVM compiler tools are available and bpf target is supported by llc
.PHONY: verify_target_bpf $(CLANG) $(LLC) $(BPFNAME)

verify_cmds: $(CLANG) $(LLC)
	@for TOOL in $^ ; do \
		if ! (which -- "$${TOOL}" > /dev/null 2>&1); then \
			echo "*** ERROR: Cannot find LLVM tool $${TOOL}" ;\
			exit 1; \
		else \
			echo "pass verify_cmds:" \
			true; fi; \
	done

verify_target_bpf: verify_cmds
	@if ! (${LLC} -march=bpf -mattr=help > /dev/null 2>&1); then \
		echo "*** ERROR: LLVM (${LLC}) does not support 'bpf' target" ;\
		echo "   NOTICE: LLVM version >= 3.7.1 required" ;\
		exit 2; \
	else \
		echo "pass verify_target_bpf:" \
		true; fi

# Compile the C code with the clang llvm compiler
# do extra CLANG so first pass can return non-zero to shell and stop make
$(BPFNAME).bc: %.bc : %.c
	@$(CLANG) $(CFLAGS) $(INCLUDES) -emit-llvm -c $< -o - > /dev/null
	$(CLANG) $(CFLAGS) $(INCLUDES) -emit-llvm -c $< -o $@

# Invoke the llvm on the generated .bc code and produce bpf byte code
$(BPFNAME).o: %.o : %.bc
	$(LLC) -march=bpf -mcpu=probe -filetype=obj $< -o $@

$(BPFNAME): % : %.o

clean:
	rm -f *.o *.bc
	rm ebpf_rate_control


# The switch target loader which attaches the xdp program to the interfaces and
# fills all relevant maps
BPF_DIR:=bpf
SRC:= hbm.c cgroup_helpers.c bpf_load.c libbpf/src/hashmap.c
USER_INCLUDES:= -Ilibbpf/include/ -Ilibbpf/include/uapi/
USER_LIBS:= bpf/usr/lib64/libbpf.a -lelf
SRC_FLAGS:= -O2 -g -D__KERNEL__ -D__ASM_SYSREG_H $(USER_INCLUDES) $(USER_LIBS)
ebpf_rate_control: hbm.c $(SRC)
	$(CLANG) $(SRC) $(SRC_FLAGS) -lelf -o $@