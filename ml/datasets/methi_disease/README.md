# Methi disease image dataset — collection in progress

**No disease-image binaries are included in this directory yet.** The repository only records authoritative disease references and a source register. Do not treat linked web figures as downloaded or reusable training images.

## Candidate labels

The official NIPHM fenugreek IPM package documents diseases and symptom descriptions. Candidate class names for expert review include:

- `healthy`
- `alternaria_leaf_blight`
- `cercospora_leaf_spot`
- `powdery_mildew`
- `downy_mildew`
- `rust`
- `root_collar_foot_rot`
- `damping_off`
- `fusarium_wilt`
- `yellow_mosaic`
- `uncertain_or_non_disease_stress`

This is a proposed image-label schema, not a claim that each class already has images or is confirmed in the local crop. Some disease names/symptom complexes may overlap; a plant pathologist should review labels.

## Source register

See `sources.csv`. The NIPHM guide is useful for the official disease list and symptom descriptions. Research articles may provide visual figures for particular pathogens, but check the licence and figure-specific credit before copying any image into this repository.

## Collection rules

1. Keep the original, unmodified image and source metadata.
2. Record the exact disease diagnosis basis: field diagnosis, lab confirmation, or literature figure.
3. Keep literature illustrations separate from real farm photographs.
4. Never combine similar-looking symptoms into one confirmed disease label without expert confirmation.
5. Split by farm/plant/session, not by random image, to prevent near-duplicate leakage.
6. Do not augment a tiny set and count the augmented outputs as independent samples.
