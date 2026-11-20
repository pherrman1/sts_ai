# Worker CPU profile of the stage-1 run driver (cloud, 2026-11-20)

`az-run-driver` (fake net, RelWithDebInfo, main 420fbb62) under a CPU-time sampler (ITIMER_PROF, backtrace per
sample, addr2line with inlined frames), cloud container (Intel Xeon 2.3 GHz, 4 cores), 3 workers x 450 games,
`--asc 5 --utility amber2-root --explore-amber --explore-per-offer --pick-target 0.01 --no-fast-noise --q-rescale
--c-scale 0.1 --chance-on-reveal --cross-combat --sim-help --force-keys --force-rewards --force-potions
--compact-samples --max-pending 0 --batch 2048`. Not the live run: random net outputs, no evaluation cache, no
merged cards, another CPU. Shares are of the samples on worker threads (inclusive unless noted).

Run A: 60 s, runs die early (mean floor 4.4), 31,117 worker samples, 196.5k evals/s.
Run B: 240 s with `--test-hp 3000` (mean floor 26.1), 111,472 worker samples, 173.7k evals/s.

| share of worker CPU, % | A (early floors) | B (late floors) |
|---|---|---|
| `cpuSeconds` (clock_gettime CLOCK_THREAD_CPUTIME_ID, for the metrics) | 11.1 | 12.4 |
| `BattleContext::operator=` (state copy) | 9.6 | 12.9 |
| `BattleContext::executeActions` (game step) | 8.0 | 10.6 |
| `amberEncodeCombat` | 6.0 | 10.4 |
| `amberEncodeGame` | 4.2 | 1.9 |
| `SilverSearcher::enumerateActions` | 5.5 | 6.8 |
| malloc + free (libc) | 11.8 | 9.1 |
| `shared_ptr` counts | 6.8 | 3.9 |
| `sampleNoncombatFuture` | 7.0 | 3.2 |
| `detachedGameCopy` | 5.8 | 3.0 |
| `vector<Edge>::clear` | 3.4 | 3.7 |
| `amberHalf` (float to half, self) | 2.6 | 3.7 |
| `selectNonRoot` | 2.0 | 2.3 |

Cost of one clock call in this container: CLOCK_THREAD_CPUTIME_ID 171 ns (a system call), CLOCK_MONOTONIC 23 ns.
With about 14 us of worker CPU per evaluation in run B that is about 10 calls per evaluation.

## Run B, self time (top)
```
--- self (worker threads)
 12.42  [[vdso]]
  4.60  
  3.66  amberHalf
  3.34  [__default_morecore@GLIBC_2.2.5]
  3.21  [__nss_database_lookup@GLIBC_2.2.5]
  2.71  [free@@GLIBC_2.2.5]
  2.42  _Vector_base<int, allocator<int> >::_M_deallocate
  2.22  BattleContext::operator=
  2.19  RunDriver::workerLoop
  1.97  CardInstance* __do_uninit_copy<__gnu_cxx::__normal_iterator<CardInstan...ance> > >, CardInstance*>
  1.79  [malloc@@GLIBC_2.2.5]
  1.52  push
  1.44  Monster::operator=
  1.43  selectNonRoot
  1.23  lambda@az_run_driver.cpp:1230
  1.23  [timer_settime@GLIBC_2.2.5]
  1.20  __gnu_cxx::__atomic_add
  1.15  lambda@az_run_driver.cpp:1224
  1.08  vector<int, allocator<int> >::capacity
  1.06  Action::Action
  1.01  BattleContext::executeActions
  1.00  memcpy
  0.78  double const& min<double>
  0.77  vector<RunDriver::Run, allocator<RunDriver::Run> >::operator[]
  0.77  vector<MonsterRollInputs, allocator<MonsterRollInputs> >::capacity
  0.75  decltype 
  0.73  SilverSearcher::enumerateCardActions
  0.71  vector<Edge, allocator<Edge> >::_M_erase_at_end
  0.63  _Vector_base<int, allocator<int> >::_Vector_impl_data::_M_copy_data
  0.62  void _Construct<Map, Map&>
--- library self by first caller in the binary
```
