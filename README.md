[![License: CC0-1.0](https://img.shields.io/badge/License-CC0%201.0-lightgrey.svg)](http://creativecommons.org/publicdomain/zero/1.0/)

## Bycon - a Python-based environment for the Beacon v2 genomics API

The `bycon` project - at least at its current stage - is a mix of _Progenetix_ (i.e. GA4GH object model derived, _MongoDB_ implemented) - data management, and the implementation of middleware & server for the Beacon API.

More information about the current status of the package can be found in the inline
documentation which is also [presented in an accessible format](https://info.progenetix.org/tags/Beacon.html) on the _Progenetix_ website.

### More Documentation

#### [ByconPlus](./bycon/doc/byconplus.md)

This page provides more information about the _Beacon_ functionality, current
implementation status and usage examples.

#### [Services](./services/doc/services.md)

The _bycon_ environment - together with the [Progenetix](http://progenetix.org)
resource - provide a growing numer of data services in (cancer) genomics and
disease ontologies. _bycon_'s services are tools to enable the APIs.

### Directory Structure

##### `bycon`

* web applications for data access
* Python modules for Beacon query and response functions in `lib`

##### `services`

* web applications and libraries extending the `bycon` environment

#### Internal structure



##### `pgy`

* applications and utilities for (Progenetix) data access & processing
* Python modules for data management in the [MongoDB](http://mongodb.org) based
_Progenetix_ database environment

##### `config`

* configuration files, separated for topic/scope
* YAML ...

##### `data/in`, `data/out`, `data/out/yaml`

* input and output for example and test data
* in `.gitignore`

##### `doc`

* documentation, in Markdown

##### `rsrc`

* various resources beyond configuration data
    - mapping input table(s)
    - external schema dumps
    - ...


