from math import comb
import requests
import json
def cal_exact(times,proper,need):
    """
    计算二项分布概率
    times: 试验次数
    proper: 单次成功概率
    need: 成功次数
    """
    return(comb(times, need) * (proper ** need) * ((1 - proper) ** (times - need)))
def cal_award(times,proper,min_proper):
    """
    计算单类成功几率，返回列表
    """
    lists=[]
    mid_proper=int(times*proper)
    for i in range(len(times)):
        proper_=cal_exact(times,proper,i)
        if i >= mid_proper and proper_<min_proper:
            break
        else:
            lists.append([i,proper_])
def cal_main(times,situation):
    """
    根据用户输入，计算概率
    """
    final=situation
    needing=situation["needing"]
    pool=situation["pool"]