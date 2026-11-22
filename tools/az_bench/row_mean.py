"""Mean over each row's tokens after the first, on packed tokens (AmberNet packed heads).

The heads pool a row as h[0] + summary_mlp(mean of the other live tokens). On the padded [B, T, d] layout that is a
masked sum over the batch's token bucket for every row; here one program per row adds up its own packed tokens
seq_off[r] + 1 .. seq_off[r + 1] (fp32 accumulation) and divides by their count (a row of one or zero tokens gives
zeros, as the padded form's clamp does). Same math as the padded masked mean up to float rounding
(tests/test_packed_heads.py, TRITON_INTERPRET=1 on a CPU).
"""

import torch
import triton
import triton.language as tl


@triton.jit
def _row_mean_kernel(X, O, OFF, D: tl.constexpr, BT: tl.constexpr):
    r = tl.program_id(0)
    start = tl.load(OFF + r)
    n = tl.load(OFF + r + 1) - start
    cols = tl.arange(0, D)
    acc = tl.zeros([D], tl.float32)
    for k0 in range(1, n, BT):   # the row's tokens after its first
        offs = k0 + tl.arange(0, BT)
        v = tl.load(X + (start + offs)[:, None] * D + cols[None, :], mask=(offs < n)[:, None], other=0.0)
        acc += tl.sum(v.to(tl.float32), 0)
    cnt = tl.maximum(n - 1, 1)
    tl.store(O + r * D + cols, (acc / cnt.to(tl.float32)).to(O.dtype.element_ty))


@triton.jit
def _row_mean_kernel_1d(X, O, OFF, D: tl.constexpr):
    # one token per step, no 2-D reduction: the [BT, D] kernel above gave wrong fp32 means at every width but 128
    # on the PC GPU (sm_86, triton 3.1.0; fp16 right at all widths), so fp32 inputs use this one
    r = tl.program_id(0)
    start = tl.load(OFF + r)
    n = tl.load(OFF + r + 1) - start
    cols = tl.arange(0, D)
    acc = tl.zeros([D], tl.float32)
    for k in range(1, n):
        acc += tl.load(X + (start + k) * D + cols).to(tl.float32)
    cnt = tl.maximum(n - 1, 1)
    tl.store(O + r * D + cols, (acc / cnt.to(tl.float32)).to(O.dtype.element_ty))


@torch.library.custom_op("azbench::row_mean", mutates_args=())
def _row_mean_op(x: torch.Tensor, seq_off: torch.Tensor) -> torch.Tensor:
    x, seq_off = x.contiguous(), seq_off.contiguous()   # the kernel indexes raw pointers
    R = seq_off.shape[0] - 1
    out = x.new_empty(R, x.shape[1])
    if x.dtype == torch.float32:
        _row_mean_kernel_1d[(R,)](x, out, seq_off, D=x.shape[1], num_warps=1)
    else:   # fp16 / bf16: the inference path (unchanged)
        _row_mean_kernel[(R,)](x, out, seq_off, D=x.shape[1], BT=32, num_warps=1)
    return out


@_row_mean_op.register_fake
def _(x, seq_off):
    return x.new_empty(seq_off.shape[0] - 1, x.shape[1])


def row_mean(x, seq_off):
    """x [N, d] contiguous packed tokens, seq_off [R + 1] int32 / int64 row starts. Returns [R, d]: per row the mean
    of its tokens after the first."""
    return _row_mean_op(x, seq_off)
