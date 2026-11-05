# DataMate on Google Colab

This folder contains a Colab notebook for GPU inference experiments and a Colab-specific dependency list. It does not train or fine-tune a model: the current repository does not yet have a training pipeline (`train.sh` is empty).

## Before opening the notebook

1. Push the code revision you want to run to a GitHub branch. This workspace currently has local commits and edits that are not all present on GitHub; the notebook clones the configured branch and cannot see unpushed workspace changes.
2. Put the competition split under Google Drive, for example `MyDrive/DataMate/competition_data/`, with `train/` and/or `public_test/` inside. The notebook copies it to `/content` before processing. `competition_data/` is intentionally ignored by Git.
3. Open `DataMate_Colab.ipynb` in Google Colab and choose **Runtime → Change runtime type → GPU**. Edit the repository branch and Drive data path in the configuration cell if needed.

## Notebook flow

The notebook checks the GPU, clones the selected branch, stages data from Drive, installs `requirements-colab.txt`, runs a three-question dry run, then evaluates a small labeled sample from `train`. An optional cell runs a resumable public-test inference batch.

The Colab dependency file deliberately omits PyTorch and the CUDA wheel index: Colab supplies PyTorch with its runtime. If the runtime has no CUDA GPU, select a GPU runtime instead of installing another PyTorch build over the Colab one.

Outputs from the labeled sample are copied to `MyDrive/DataMate/colab_runs/`. The public-test submission is written directly to Drive so `predict.py --resume` can continue in a later session; per-question logs stay on the local runtime during inference and are archived to Drive afterward.

## Competition packaging

Colab is for interactive development and benchmarking. It downloads dependencies and model weights as needed. The competition package still needs a separate offline Docker environment and must include its model weights before inference starts.
