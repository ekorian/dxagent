# Diagnostic Agent Ressources

* `input.csv`
   An informative list of vendor-specific monitored fields.
   
* `metrics.csv`
   A list of vendor-independent performance metrics.

* `rules.csv`
   A list of symptoms.
   
### `input.csv`

This file contains a list of vendor-specific input fields. Each field is described
by the following attributes: category, name, type (e.g., str, int or float), 
counter (1 if the field is a counter, 0 if it is not), unit, and index (e.g.,
how this field is indexed).

`input.csv` is purely informative and not used in DxAgent at the moment.

### `metric.csv`

This file contains a list of metrics, which are *standard* vendor-independent
performance indicators fields. Each metric is defined by the following attributes:
name, subservice, type (e.g., str, int or float), is_list (1 if this field is contained in
a list, 0 if it is not) and unit. `subservice` can be:

* cpu, sensors, disk, mem, proc, net, if

`metric.csv` is used by DxAgent, do not modify it.

### `rules.csv`

This file is the list of symptoms, it is used to determine a subservice health.
Each symptom is defined by a name, (e.g., "Swap volume in use"), a severity (e.g.,
Orange or Red), and a rule. Rules are boolean expressions using metrics as variables
and the following operators (i,e., similar to Python's):

* `and`, `or` and parentheses (i.e., grouping operators).

* `>`, `<`, `>=`, `<=`, `==`, `!=`

* `any()`, `all()` return `True` if the expression inside returns `True` for
respectively at least one element, and all elements, of the list in which it
is contained (i.e., is_list). For instance, `all(bm_cpu_user_time>95)` is
`True` if all CPUs are 95% busy.

* 1min(), 5min() return `True` if the expression inside is `True`
for the given period of time.


If a symptom is superseeding another, its rule should specifically exclude the rule of
the superseeded symptom, and reciprocally.
