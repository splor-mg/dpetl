# Example datapackage

The following example shows a complete `datapackage.yaml` configuration.

Note that `dpetl_extract` and `dpetl_transform` are defined per resource, while `dpetl_load` is defined at the package level.

```yaml
resources:
{% include "extract.yaml" %}

{% include "transform.yaml" %}

{% include "load.yaml" %}
```
