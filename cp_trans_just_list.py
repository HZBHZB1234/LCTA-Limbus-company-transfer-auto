import json
from translate import *
import shutil
import os
import jsonpatch
def get_json_from(fromlan,en,kor):
    if fromlan=='jp' or fromlan=='kor':
        return en
    else:return kor
def get_json_target(fromlan,en,kor,jp):
    if fromlan=='en':
        return en
    elif fromlan=='kor':
        return kor
    else:return jp
def mymovefile(srcfile,dstpath,with_let,in_folder):                       # 移动函数
    fpath,fname=os.path.split(srcfile)             # 分离文件名和路径
    if (not in_folder=='') and (not os.path.exists(dstpath+'\\'+in_folder[:-1])):
        os.makedirs(dstpath+'\\'+in_folder[:-1])
    if with_let:
        shutil.copy(srcfile, dstpath +'\\'+ in_folder + fname[3:])
    else:
        shutil.copy(srcfile, dstpath +'\\'+ in_folder +fname)          # 移动文件
def make_id_list(list):
    result=[]
    for i in list:
        if not i=={}:
            try:
                result.append(i['id'])
            except:
                result.append(None)
    return result
def make_id_list_true(list):
    result=[]
    for i in list:
        try:
            result.append(i['id'])
        except:
            result.append(None)
    return result
def all_trans(json_for,json_to,fromlang,inter,appid,appkey):
    diff=jsonpatch.JsonPatch.from_diff(json_for,json_to)
    for i in diff:
        if i['op']=='replace':
            after=translate_final(fromlang,'zh',i['value'],inter,appid,appkey)
            print(after)
            i['value']=after
    returnz=jsonpatch.apply_patch(json_for,diff)
    return returnz
def cp_trans(path_limbus,path_llc,name,path_output,from_lang,intervene,appids,appkeys):
    name_path=(os.path.split(name))[0]
    if not name_path=='':
        name_path=name_path+'\\'
    name_file=(os.path.split(name))[1]
    path_en=path_limbus+'LimbusCompany_Data\Assets\Resources_moved\Localize\en\\'+name_path+'EN_'+name_file
    path_kor=path_limbus+'LimbusCompany_Data\Assets\Resources_moved\Localize\kr\\'+name_path+'KR_'+name_file
    path_jp=path_limbus+'LimbusCompany_Data\Assets\Resources_moved\Localize\jp\\'+name_path+'JP_'+name_file
    path_llc=path_llc+'\\'+name
    if name_file=='E000X.json' :
        print('零协未翻译的愚人节内容')
        mymovefile(path_en,path_output,True,name_path)
        return 0
    with open(path_en, 'rb') as file:
        json_en=json.load(file) 
    with open(path_kor, 'rb') as file:
        json_kor=json.load(file)
    with open(path_jp, 'rb') as file:
        json_jp=json.load(file)
    llc_exist=True
    if os.path.exists(path_llc):
        with open(path_llc, 'rb') as file:
            json_llc=json.load(file)
    else:llc_exist=False
    #获取列表内容
    if json_en=={}:
        mymovefile(path_en,path_output,True,name_path)
        return 0
    list_en=json_en['dataList']
    list_kor=json_kor['dataList']
    list_jp=json_jp['dataList']
    if list_en==[] or list_en==[{}]:
        mymovefile(path_en,path_output,True,name_path)
        return 0
    id_en=make_id_list(list_en)
    #id_jp=make_id_list(list_jp)
    #id_kor=make_id_list(list_kor)
    if llc_exist:
        list_llc=json_llc['dataList']
        id_llc=make_id_list(list_llc)
        if id_en==id_llc:
            mymovefile(path_llc,path_output,False,name_path)
        else:
            just_none=True
            for i in id_en:
                if not i==None:
                    just_none=False
            if just_none and len(id_en)==len(id_llc):
                mymovefile(path_llc,path_output,False,name_path)
            else:
                id_llc_true=make_id_list_true(list_llc)
                id_target_true=make_id_list_true(get_json_target(from_lang,json_en,json_kor,json_jp)['dataList'])
                id_for_true=make_id_list_true(get_json_from(from_lang,json_en,json_kor)['dataList'])
                if just_none:
                    print('检测到例外数据，默认未翻译')
                    print('相对路径为'+name)
                    print('绝对路径(零协路径)'+path_llc)
                    print('请检查是否需要翻译')
                    trans_do=''
                    while not (trans_do=='tran' or trans_do=='for' or trans_do=='llc'):
                        print('需要翻译输入tran，使用原文输入for，使用零协输入llc')
                        trans_do=input()
                    if trans_do=='tran':
                        with open(path_output+'\\'+name,'w',encoding='utf-8') as f:
                            json.dump(all_trans(get_json_from(from_lang,json_en,json_kor),get_json_target(from_lang,json_en,json_kor,json_jp),from_lang,intervene,appids,appkeys), f,ensure_ascii=False,indent=4)
                    elif trans_do=='for':
                        mymovefile(path_en,path_output,True,name_path)
                    else:
                        mymovefile(path_llc,path_output,False,name_path)
                else:
                    final_list=[]
                    for i in id_target_true:
                        try:
                            id_in_llc=id_llc_true.index(i)+1
                        except:
                            id_in_llc=False
                        if id_in_llc:
                            final_list.append(list_llc[id_in_llc-1])
                        else:
                            json_for=get_json_from(from_lang,json_en,json_kor)['dataList'][id_for_true.index(i)]
                            json_target=get_json_target(from_lang,json_en,json_kor,json_jp)['dataList'][id_target_true.index(i)]
                            diff=jsonpatch.JsonPatch.from_diff(json_for,json_target)
                            for im in diff:
                                if im['op']=='replace':
                                    after=translate_final(from_lang,'zh',im['value'],intervene,appids,appkeys)
                                    print(after)
                                    im['value']=after
                            final_list.append(jsonpatch.apply_patch(json_for,diff))
                    ret={}
                    ret['dataList']=final_list
                    with open(path_output+'\\'+name,'w',encoding='utf-8') as f:
                        json.dump(ret,f,ensure_ascii=False,indent=4)
    else:
        print(path_en+'    llc文件不存在')
        with open(path_output+'\\'+name,'w',encoding='utf-8') as f:
            json.dump(all_trans(get_json_from(from_lang,json_en,json_kor),get_json_target(from_lang,json_en,json_kor,json_jp),from_lang,intervene,appids,appkeys), f,ensure_ascii=False,indent=4)

    #判断零协是否翻译


#    if id_en==id_llc:
#        shutil.copy(path_llc,path_output+'\\'+name)
#    else:
#        print(path_en)
#cp_trans('C:\Program Files (x86)\Steam\steamapps\common\Limbus Company\\','C:\Program Files (x86)\Steam\steamapps\common\Limbus Company\LimbusCompany_Data\lang\LLC_CN','StoryData\P11012.json','output\\测试输出','kor',0,'20250405002325015','NMyimh3GSnQm0DUaum1C')
    