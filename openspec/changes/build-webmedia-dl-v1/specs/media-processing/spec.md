# Delta: media-processing

## ADDED Requirements

### Requirement: Separate remux and transcode

`process.ffmpeg.remux` SHALL use stream copy. `process.ffmpeg.transcode` SHALL use
allowlisted codecs only. ImageMagick SHALL run with a restrictive policy file and
typed input/output paths. The runtime SHALL set `MAGICK_CONFIGURE_PATH` to
`resources/imagemagick-runtime`.

#### Scenario: remux argv

- **WHEN** remux is requested
- **THEN** argv contains `-c copy` and does not accept user-supplied extra flags

#### Scenario: ImageMagick policy directory

- **WHEN** a subprocess is launched
- **THEN** `MAGICK_CONFIGURE_PATH` points at a directory containing `policy.xml`
