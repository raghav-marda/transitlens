# TransitLens evaluation report

## oracle

Overall accuracy **100.0%** on 84 tasks (95% CI 95.6% to 100.0%); 0 failed calls excluded.

### By skill

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| counterfactual_reasoning | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| counting | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| interchange_identification | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| legend_matching | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| line_tracing | 12/12 | 100.0% | 76% to 100% | low n, do not rank |
| route_planning | 16/16 | 100.0% | 81% to 100% | low n, do not rank |

### By question kind

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| connecting_station | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| interchange_count | 16/16 | 100.0% | 81% to 100% | low n, do not rank |
| line_length | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| lines_at | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| reroute | 14/14 | 100.0% | 78% to 100% | low n, do not rank |
| stops_between | 12/12 | 100.0% | 76% to 100% | low n, do not rank |

### By station-less crossings

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| no crossings | 30/30 | 100.0% | 89% to 100% |  |
| with station-less crossings | 54/54 | 100.0% | 93% to 100% |  |

### By number of lines

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| 3 lines | 30/30 | 100.0% | 89% to 100% |  |
| 4 lines | 30/30 | 100.0% | 89% to 100% |  |
| 5 lines | 24/24 | 100.0% | 86% to 100% |  |

### By colour palette

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| cb_safe | 36/36 | 100.0% | 90% to 100% |  |
| classic | 48/48 | 100.0% | 93% to 100% |  |

### By station-name script

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| devanagari | 42/42 | 100.0% | 92% to 100% |  |
| latin | 42/42 | 100.0% | 92% to 100% |  |

## random

Overall accuracy **8.3%** on 84 tasks (95% CI 4.1% to 16.2%); 0 failed calls excluded.

### By skill

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| counterfactual_reasoning | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| counting | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| interchange_identification | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| legend_matching | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| line_tracing | 4/12 | 33.3% | 14% to 61% | low n, do not rank |
| route_planning | 3/16 | 18.8% | 7% to 43% | low n, do not rank |

### By question kind

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| connecting_station | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| interchange_count | 3/16 | 18.8% | 7% to 43% | low n, do not rank |
| line_length | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| lines_at | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| reroute | 0/14 | 0.0% | 0% to 22% | low n, do not rank |
| stops_between | 4/12 | 33.3% | 14% to 61% | low n, do not rank |

### By station-less crossings

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| no crossings | 2/30 | 6.7% | 2% to 21% |  |
| with station-less crossings | 5/54 | 9.3% | 4% to 20% |  |

### By number of lines

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| 3 lines | 1/30 | 3.3% | 1% to 17% |  |
| 4 lines | 1/30 | 3.3% | 1% to 17% |  |
| 5 lines | 5/24 | 20.8% | 9% to 40% |  |

### By colour palette

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| cb_safe | 3/36 | 8.3% | 3% to 22% |  |
| classic | 4/48 | 8.3% | 3% to 20% |  |

### By station-name script

| Bucket | Correct / total | Accuracy | 95% CI | Note |
|---|---|---|---|---|
| devanagari | 2/42 | 4.8% | 1% to 16% |  |
| latin | 5/42 | 11.9% | 5% to 25% |  |
