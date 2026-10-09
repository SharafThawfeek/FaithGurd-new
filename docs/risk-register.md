# Risk register

Review this at every weekly integration check and at every phase gate. When an early warning appears, apply the fallback and record it in the decision log.

**Status values:** *watching*, *triggered* (fallback in use), *closed*.

| ID | Risk | Early warning | Fallback | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| R-01 | Labelling is slower than 4 minutes per item | Pilot rate above 6 minutes | Cut US groups to 120 first; keep all Sri Lankan groups | All | watching |
| R-02 | fp16 LoRA fails on a T4 | Repair pilot verdict FAIL | QLoRA with fp32 maths; then Qwen3 1.7B; then 0.6B; then a prompt-only repairer | M.S.A Ahamed | watching |
| R-03 | Generators make very few errors | Pilot error rate below about 10% | Report it as a finding that bounds the benefit; add harder question types | All | watching |
| R-04 | XBRL negatives do not help | No recall gain on development data | Report as a negative result; the slot head and shift study still stand | M.L Ahamed | watching |
| R-05 | α = 0.10 is not certifiable | Feasibility bound fails at the calibration size | Report the certification-budget curve as the finding | Sharaf | watching |
| R-06 | A teammate's part is late | A handover in phase 4 is missed | Switch to the fallback input in the phase plan's handover table | Each member | watching |
| R-07 | Sri Lankan report terms block release | No answer from the CSE or the companies | Release questions, labels and page pointers only, not PDFs | All | watching |
| R-08 | A new paper overlaps a contribution | Literature refresh at a gate | Narrow the claim and cite it; never hide it | Each member | watching |
| R-09 | Free GPU quota is cut or runs out | Quota record changes; hours used pass the budget | Precomputed outputs; Sharaf's spare quota; switch between Kaggle and Colab; apply the cut list | All | watching |
| R-10 | Qwen3.5 uses linear-attention (Gated DeltaNet) layers whose fast kernels may not run on a T4, so training is slow or runs out of memory | Repair pilot reports the slow fallback path or low tokens per second | Try the `flash-linear-attention` kernels in the pilot; otherwise move down the D-003 chain to Qwen3 1.7B, which uses standard attention | M.S.A Ahamed | watching |
| R-11 | LettuceDetect v2 (June 2026) ships a typed "taxonomy head", which overlaps the detector's relation-slot head | Found on 2026-10-08 while checking model files | Read it in phase 1; keep the claim to financial relation slots trained with XBRL-mined negatives, and compare against it | M.L Ahamed | watching |
| R-12 | The prebuilt llama.cpp binary does not run on the Kaggle or Colab system | Generation pilot falls back to a source build | The pilot builds llama.cpp from source automatically (adds roughly 10–20 minutes, one time) | Sharaf | watching |
| R-13 | Option B's extra calibration issuers (D-007) make table correction too slow | Table correction falls behind question writing in phase 3 | Switch to option A: split the existing issuers between calibration and test | All | watching |
| R-14 | The policy certificate assumes independent answers, but answers about one company are related | Examiner or reviewer question | Pre-register an issuer-level sensitivity check (phase 4) | Sharaf | watching |
| R-15 | SEC access is blocked until a real contact email is declared | `faithguard` EDGAR calls raise SecAccessError | Set `FG_SEC_USER_AGENT`; US CIKs and XBRL facts wait until then | Sharaf | closed (2026-10-09: contact declared, SEC accepts requests) |
| R-16 | Numbers in report text are weak evidence: the sentence's context is guessed | Controlled-track errors traced to passages | D-017 makes them unverifiable unless the sentence names the metric; Channel A (phase 4) reads text better | M.L Ahamed | watching |
| R-17 | Template answers on the controlled track are cleaner than real model answers, so rule-only numbers there overstate real performance | Pilot answers (phase 3) score worse than the controlled track | Report controlled-track numbers only as pipeline checks; all claims rest on the human-labelled natural test | All | watching |
| R-18 | Repair fine-tuning on about 10,000 examples takes longer on a T4 than budgeted | The first checkpoint's steps per hour | Train on a subset (`--limit`) or half an epoch; checkpoints resume across sessions | M.S.A Ahamed | watching |
| R-19 | SCoRE's guarantee holds only in expectation and is sensitive to tied scores | Its observed risk varies around alpha between subsamples | Report it as a comparator with its guarantee stated; break ties at random (D-025) | Sharaf | watching |
| R-20 | On template answers the rule checker almost determines outcomes, so learned policy models look near-perfect (AUROC 0.99) | Controlled-track AUROC near 1 | Treat controlled-track policy numbers as a rehearsal; the paper's comparison is on the natural benchmark | Sharaf | watching |
| R-21 | Kaggle runs notebooks without a GPU or internet on accounts that are not phone-verified, even when both are requested | Notebooks stop at the first cell with "No internet in this session" (seen 2026-10-09 on all three pilots) | Verify the phone number in Kaggle settings, then re-run with `python pilots/kaggle_run.py push`; or run the notebooks on Colab | Sharaf | triggered |
| R-22 | A test issuer stops filing before its next annual report, shrinking the future-period set | Form 15 or 25 filings, or a ticker missing from the SEC or CSE list (2 of 32 US candidates stopped filing in 2026) | Run the future-period check on the test issuers that still report, and state the count | Sharaf | watching |
