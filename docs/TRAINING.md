# Preparing future training data

Retrieval supplies updatable background. Fine-tuning trains selected behaviors or capabilities. Keeping an archive does not create a high-quality training set by itself.

Select samples by platform, account, and project. Review roles, evidence and answer quality: a user question does not mean the assistant's answer was endorsed. Restore individual paths in branched exports instead of concatenating parallel branches. Distinguish original attachments from preview screenshots.

Keep reviewed samples in the private training/ directory, separate from ordinary memory. Retain source_path, source_sha256, message_indices, review_status, purpose, and split. Split by whole conversations and group near-duplicates together to prevent leakage. Convert to the selected model's required format only after choosing a training target.

This project does not run fine-tuning or automatically label archive text as approved training data.
