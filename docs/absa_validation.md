# ABSA validation of aspect sentiment

Model: `yangheng/deberta-v3-base-absa-v1.1`. Sentences checked: 366.

- Agreement with our scores: **89.1%**
- Cohen's kappa: **0.766** (1 = perfect, 0 = chance)

| Aspect | Sentences | Agreement |
| --- | --- | --- |
| delivery | 60 | 96.7% |
| ease of use | 60 | 71.7% |
| packaging | 60 | 91.7% |
| price | 60 | 90.0% |
| quality | 60 | 88.3% |
| results | 60 | 95.0% |
| scent | 6 | 100.0% |

Rows are our label, columns are the ABSA model's label.

| ours \ ABSA | neg | neu | pos |
| --- | --- | --- | --- |
| neg | 95 | 2 | 10 |
| neu | 9 | 0 | 15 |
| pos | 0 | 4 | 231 |
