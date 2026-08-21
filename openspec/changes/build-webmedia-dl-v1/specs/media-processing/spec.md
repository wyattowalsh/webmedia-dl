# Delta: media-processing

## ADDED Requirements

### Requirement: Separate remux and transcode

`process.ffmpeg.remux` SHALL use stream copy. `process.ffmpeg.transcode` SHALL use
allowlisted codecs only. ImageMagick SHALL run with a restrictive policy file and
typed input/output paths.

#### Scenario: remux argv

- **WHEN** remux is requested
- **THEN** argv contains `-c copy` and does not accept user-supplied extra flags
