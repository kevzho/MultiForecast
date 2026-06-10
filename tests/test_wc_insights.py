from worldcup import insights


def make_result_stub():
    # 2 groups (A,B), 4 teams each
    teams_A = ["A1", "A2", "A3", "A4"]
    teams_B = ["B1", "B2", "B3", "B4"]
    per_team = {}
    per_group = {"A": {}, "B": {}}
    # create simple distributions
    for t in teams_A:
        if t == "A1":
            per_team[t] = {
                "P(win_cup)": 0.15,
                "P(reach_Final)": 0.25,
                "P(reach_SF)": 0.35,
                "P(reach_QF)": 0.5,
                "P(advance)": 0.8,
                "P(win_group)": 0.6,
                "P(top2_in_group)": 0.85,
                "finish_distribution": {"1st": 0.6, "2nd": 0.25, "3rd": 0.1, "4th": 0.05},
            }
        elif t == "A2":
            per_team[t] = {
                "P(win_cup)": 0.05,
                "P(reach_Final)": 0.1,
                "P(reach_SF)": 0.15,
                "P(reach_QF)": 0.2,
                "P(advance)": 0.7,
                "P(win_group)": 0.25,
                "P(top2_in_group)": 0.6,
                "finish_distribution": {"1st": 0.25, "2nd": 0.45, "3rd": 0.2, "4th": 0.1},
            }
        else:
            per_team[t] = {
                "P(win_cup)": 0.01,
                "P(reach_Final)": 0.02,
                "P(reach_SF)": 0.03,
                "P(reach_QF)": 0.05,
                "P(advance)": 0.2,
                "P(win_group)": 0.15,
                "P(top2_in_group)": 0.25,
                "finish_distribution": {"1st": 0.15, "2nd": 0.25, "3rd": 0.3, "4th": 0.3},
            }
        per_group["A"][t] = per_team[t]["finish_distribution"]

    for t in teams_B:
        if t == "B1":
            per_team[t] = {
                "P(win_cup)": 0.2,
                "P(reach_Final)": 0.35,
                "P(reach_SF)": 0.45,
                "P(reach_QF)": 0.6,
                "P(advance)": 0.9,
                "P(win_group)": 0.7,
                "P(top2_in_group)": 0.9,
                "finish_distribution": {"1st": 0.7, "2nd": 0.2, "3rd": 0.07, "4th": 0.03},
            }
        else:
            per_team[t] = {
                "P(win_cup)": 0.02,
                "P(reach_Final)": 0.03,
                "P(reach_SF)": 0.04,
                "P(reach_QF)": 0.06,
                "P(advance)": 0.25,
                "P(win_group)": 0.1,
                "P(top2_in_group)": 0.3,
                "finish_distribution": {"1st": 0.1, "2nd": 0.2, "3rd": 0.35, "4th": 0.35},
            }
        per_group["B"][t] = per_team[t]["finish_distribution"]

    return {"per_team": per_team, "per_group": per_group}


def test_qualification_table_sorted_and_most_likely_finish():
    res = make_result_stub()
    table = insights.qualification_table(res, "A")
    # sorted by p_advance desc
    paves = [r["p_advance"] for r in table]
    assert all(paves[i] >= paves[i+1] for i in range(len(paves)-1))
    # most_likely_finish matches argmax
    for row in table:
        t = row["team"]
        fd = res["per_team"][t]["finish_distribution"]
        assert row["most_likely_finish"] == max(fd.items(), key=lambda x: x[1])[0]


def test_title_contenders_sorted():
    res = make_result_stub()
    top = insights.title_contenders(res, top_n=3)
    pwin = [r["p_win_cup"] for r in top]
    assert all(pwin[i] >= pwin[i+1] for i in range(len(pwin)-1))


def test_narratives_and_zeros_do_not_raise():
    res = make_result_stub()
    # make a zeroed team to ensure no crashes
    res["per_team"]["A4"] = {k: 0.0 for k in res["per_team"]["A4"].keys()}
    s = insights.group_stage_narrative(res, "A")
    assert isinstance(s, str) and "%" in s
    # headline
    h = insights.headline(res)
    assert isinstance(h, str) and "%" in h
