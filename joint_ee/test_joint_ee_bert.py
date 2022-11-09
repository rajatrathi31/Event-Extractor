import math
import torch
import torch.autograd as autograd
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import datetime
import json
from tqdm import tqdm


#from pytorch_transformers import BertTokenizer, BertModel, AdamW
from transformers import BertTokenizer, BertModel, AdamW

# In[111]:


import os
from recordclass import recordclass
from collections import OrderedDict
import numpy as np
import random
import pickle

def custom_print(*msg):
    for i in range(0, len(msg)):
        if i == len(msg) - 1:
            print(msg[i])
            logger.write(str(msg[i]) + '\n')
        else:
            print(msg[i], ' ', end='')
            logger.write(str(msg[i]))



def is_full_match(triplet, triplets):
    for t in triplets:
        if t[0] == triplet[0] and t[1] == triplet[1] and t[2] == triplet[2] and t[4] == triplet[4]:
            return True
    return False



def get_gt_triples(src_words, rels, pointers, event_list, arg_list):
    ##[2,45,67,10],[2,5,13,7],[(1,2,6,7),(7,8,10,10),..],[23,33,1,8]
    touples = []#
    i = 0
    for r in rels:
        arg1 = ' '.join(src_words[pointers[i][0]:pointers[i][1] + 1])#trigger phrase
        arg2 = ' '.join(src_words[pointers[i][2]:pointers[i][3] + 1])#argument phrase
        touplet = (arg1.strip(), eventIdxToName[event_list[i]], arg2.strip(), argIdxToName[arg_list[i]], relIdxToName[r])
        if not is_full_match(touplet, touples):
            touples.append(touplet)
        i += 1
    '''
    for e in event_list:
        arg1 = ' '.join(src_words[pointers[i][0]:pointers[i][1] + 1])
        arg2 = ' '.join(src_words[pointers[i][2]:pointers[i][3] + 1])
        touplet = (arg1.strip(), eventIdxToName[e], arg2.strip(), argIdxToName[arg_list[i]], relIdxToName[rels[i]])
        if not is_full_match(touplet, touples):
            touples.append(touplet)
        i += 1
    '''
    return touples


# In[117]:


def get_answer_pointers(arg1start_preds, arg1end_preds, arg2start_preds, arg2end_preds, sent_len):
    arg1_prob = -1.0
    arg1start = -1
    arg1end = -1
    max_ent_len = 38#5
    max_trig_len = 7#
    for i in range(0, sent_len):
        for j in range(i, min(sent_len, i + max_trig_len)):#
            if arg1start_preds[i] * arg1end_preds[j] > arg1_prob:
                arg1_prob = arg1start_preds[i] * arg1end_preds[j]
                arg1start = i
                arg1end = j

    arg2_prob = -1.0
    arg2start = -1
    arg2end = -1
    for i in range(0, arg1start):
        for j in range(i, min(arg1start, i + max_ent_len)):#
            if arg2start_preds[i] * arg2end_preds[j] > arg2_prob:
                arg2_prob = arg2start_preds[i] * arg2end_preds[j]
                arg2start = i
                arg2end = j
    for i in range(arg1end + 1, sent_len):
        for j in range(i, min(sent_len, i + max_ent_len)):#
            if arg2start_preds[i] * arg2end_preds[j] > arg2_prob:
                arg2_prob = arg2start_preds[i] * arg2end_preds[j]
                arg2start = i
                arg2end = j

    arg2_prob1 = -1.0
    arg2start1 = -1
    arg2end1 = -1
    for i in range(0, sent_len):
        for j in range(i, min(sent_len, i + max_ent_len)):#
            if arg2start_preds[i] * arg2end_preds[j] > arg2_prob1:
                arg2_prob1 = arg2start_preds[i] * arg2end_preds[j]
                arg2start1 = i
                arg2end1 = j

    arg1_prob1 = -1.0
    arg1start1 = -1
    arg1end1 = -1
    for i in range(0, arg2start1):
        for j in range(i, min(arg2start1, i + max_trig_len)):#
            if arg1start_preds[i] * arg1end_preds[j] > arg1_prob1:
                arg1_prob1 = arg1start_preds[i] * arg1end_preds[j]
                arg1start1 = i
                arg1end1 = j
    for i in range(arg2end1 + 1, sent_len):
        for j in range(i, min(sent_len, i + max_trig_len)):
            if arg1start_preds[i] * arg1end_preds[j] > arg1_prob1:
                arg1_prob1 = arg1start_preds[i] * arg1end_preds[j]
                arg1start1 = i
                arg1end1 = j
    if arg1_prob * arg2_prob > arg1_prob1 * arg2_prob1:
        return arg1start, arg1end, arg2start, arg2end
    else:
        return arg1start1, arg1end1, arg2start1, arg2end1


# In[118]:


def get_pred_triples(rel, arg1s, arg1e, arg2s, arg2e, eTypes, aTypes, src_words):
    touples = []
    all_touples = []

    for i in range(0, len(rel)):

        s1, e1, s2, e2 = get_answer_pointers(arg1s[i], arg1e[i], arg2s[i], arg2e[i], len(src_words))
        if s1 == 0 or e1 == 0 :
            break
        r = np.argmax(rel[i][1:]) + 1
        ev = np.argmax(eTypes[i][1:]) + 1#event type can not be <pad> or <None>
        at = np.argmax(aTypes[i][1:]) + 1


        arg1 = ' '.join(src_words[s1: e1 + 1])#trigger phrase
        arg2 = ' '.join(src_words[s2: e2 + 1])#argument phrase
        arg1 = arg1.strip()
        arg2 = arg2.strip()
        if arg1 == arg2:
            continue
        touplet = (arg1, eventIdxToName[ev], arg2, argIdxToName[at], relIdxToName[r])
        if (touplet[0], touplet[1], touplet[2]) in [(t[0], t[1],t[2]) for t in touples]:#same (trigger, argument) pair can not have two different role
        	continue
        all_touples.append(touplet)
        if not is_full_match(touplet, touples):
            touples.append(touplet)
    '''

    for i in range(0, len(eTypes)):
        r = np.argmax(rel[i][1:]) + 1
        if r == relnameToIdx['None']:
            break
        s1, e1, s2, e2 = get_answer_pointers(arg1s[i], arg1e[i], arg2s[i], arg2e[i], len(src_words))
        arg1 = ' '.join(src_words[s1: e1 + 1])
        arg2 = ' '.join(src_words[s2: e2 + 1])
        arg1 = arg1.strip()
        arg2 = arg2.strip()
        if arg1 == arg2:
            continue
        triplet = (arg1, arg2, relIdxToName[r])
        all_triples.append(triplet)
        if not is_full_match(triplet, triples):
            triples.append(triplet)
    '''
    return touples, all_touples


# In[119]:




def get_F1(data, preds):
    gt_pos = 0
    pred_pos = 0
    total_pred_pos = 0
    correct_pos = 0
    ti=0
    tc=0
    ai=0
    ro=0
    for i in range(0, len(data)):
        ##[2,45,67,10],[2,5,13,7],[(1,2,6,7),(7,8,10,10),..],[23,33,1,8]
        gt_triples = get_gt_triples(data[i].SrcWords, data[i].TrgRels, data[i].TrgPointers, data[i].eventTypes, data[i].argTypes)

        pred_triples, all_pred_triples = get_pred_triples(preds[0][i], preds[1][i], preds[2][i], preds[3][i],
                                                          preds[4][i], preds[5][i], preds[6][i], data[i].SrcWords)
        total_pred_pos += len(all_pred_triples)
        gt_pos += len(gt_triples)
        pred_pos += len(pred_triples)
        for gt_triple in gt_triples:
            if is_full_match(gt_triple, pred_triples):
                correct_pos += 1

            if gt_triple[0] in [pred[0] for pred in pred_triples]:
                ti+=1

            if gt_triple[:2] in [pred[:2] for pred in pred_triples]:
                tc+=1

            if gt_triple[1:3] in [pred[1:3] for pred in pred_triples]:
                ai+=1

            if (gt_triple[1], gt_triple[2], gt_triple[4]) in [(pred[1], pred[2], pred[4]) for pred in pred_triples]:
                ro+=1

    #print(total_pred_pos)
    return pred_pos, gt_pos, correct_pos, ti, tc, ai, ro






def get_data(src_lines, trg_lines, pos_lines, ent_lines, dep_lines, datatype):
    samples = []
    uid = 1
    for i in range(0, len(src_lines)):#for each line
        src_line = src_lines[i].strip()
        trg_line = trg_lines[i].strip()
        pos_line = pos_lines[i].strip()
        ent_line = ent_lines[i].strip()
        dep_line = dep_lines[i].strip()

        src_words = src_line.split()
        word_pos_tags = pos_line.split()####
        word_ent_tags = ent_line.split()####
        word_dep_tags = dep_line.split()

        trg_rels = []#holds relations present in a sentence
        trg_events=[]#holds events present in a sentence
        trg_args=[]#holds arguments present in a sentence
        trg_pointers = []#holds tuples containg records per relation
        parts = trg_line.split('|')
        '''
        if datatype == 1:
            random.shuffle(parts)
        '''

        #adj_data = json.loads(adj_lines[i])#skip
        #adj_mat = get_adj_mat(len(src_words), adj_data['adj_mat'])#skip

        tuples_in=[]
        for part in parts:
            elements = part.strip().split()
            tuples_in.append((int(elements[0]), int(elements[1]), eventnameToIdx[elements[2]], int(elements[3]), int(elements[4]), argnameToIdx[elements[5]], relnameToIdx[elements[6]]))

        if datatype ==1:
            tuples_in = sorted(tuples_in, key = lambda element: (element[0], element[3]))
        for elements in tuples_in:
            #elements = part.strip().split()
            #print(elements)
            trg_rels.append(elements[6])#relation index (corresponding to the relation_name from relation_vocab)
            trg_events.append(elements[2])#event index
            trg_args.append(elements[5])#arg index
            trg_pointers.append((int(elements[0]), int(elements[1]), int(elements[3]), int(elements[4])))#all the records like event-start_index, end_index, entity- start_index, end_index

        if datatype == 1 and (len(src_words) > max_src_len or len(trg_rels) > max_trg_len):#if cross max_sentence_length or max_trg_length(max no of relation tuples present in the sentence)
            #print(src_line)
            #print(trg_line)
            continue

        sample = Sample(Id=uid, SrcLen=len(src_words), SrcWords=src_words, PosTags=word_pos_tags, EntTags=word_ent_tags, DepTags=word_dep_tags, TrgLen=len(trg_rels), TrgRels=trg_rels,
                        TrgPointers=trg_pointers, eventTypes=trg_events, argTypes=trg_args)#recordclass("Sample", "Id SrcLen SrcWords TrgLen TrgRels eventTypes argTypes TrgPointers")
        samples.append(sample)
        uid += 1
    return samples


# In[113]:


def read_data(src_file, trg_file, pos_file, ent_file, dep_file, datatype):
    reader = open(src_file)
    src_lines = reader.readlines()
    reader.close()

    reader = open(trg_file)
    trg_lines = reader.readlines()
    reader.close()

    reader = open(pos_file)
    pos_lines = reader.readlines()
    reader.close()

    reader = open(ent_file)
    ent_lines = reader.readlines()
    reader.close()

    reader = open(dep_file)
    dep_lines = reader.readlines()
    reader.close()
    # l = 1000
    # src_lines = src_lines[0:min(l, len(src_lines))]
    # trg_lines = trg_lines[0:min(l, len(trg_lines))]
    # adj_lines = adj_lines[0:min(l, len(adj_lines))]

    data = get_data(src_lines, trg_lines, pos_lines, ent_lines, dep_lines, datatype)#call get_data()
    return data#list of records, records are of type Sample


# In[114]:

def get_relations(file_name):
    nameToIdx = OrderedDict()#dictionary{key=name. value=idx}
    idxToName = OrderedDict()#dictionary{key=idx, value=name}
    reader = open(file_name)
    lines = reader.readlines()
    reader.close()
    nameToIdx['<PAD>'] = 0
    idxToName[0] = '<PAD>'
    # nameToIdx['<SOS>'] = 1
    # idxToName[1] = '<SOS>'
    #nameToIdx['None'] = 1
    #idxToName[1] = 'None'
    idx = 1
    for line in lines:
        nameToIdx[line.strip()] = idx
        idxToName[idx] = line.strip()
        idx += 1
    return nameToIdx, idxToName

def get_events(file_name):
    nameToIdx = OrderedDict()#dictionary{key=name. value=idx}
    idxToName = OrderedDict()#dictionary{key=idx, value=name}
    reader = open(file_name)
    lines = reader.readlines()
    reader.close()
    nameToIdx['<PAD>'] = 0
    idxToName[0] = '<PAD>'
    # nameToIdx['<SOS>'] = 1
    # idxToName[1] = '<SOS>'
    #nameToIdx['None'] = 1
    #idxToName[1] = 'None'
    idx = 1
    for line in lines:
        nameToIdx[line.strip()] = idx
        idxToName[idx] = line.strip()
        idx += 1
    return nameToIdx, idxToName

def get_arguments(file_name):
    nameToIdx = OrderedDict()#dictionary{key=name. value=idx}
    idxToName = OrderedDict()#dictionary{key=idx, value=name}
    reader = open(file_name)
    lines = reader.readlines()
    reader.close()
    nameToIdx['<PAD>'] = 0
    idxToName[0] = '<PAD>'
    # nameToIdx['<SOS>'] = 1
    # idxToName[1] = '<SOS>'
    #nameToIdx['None'] = 1
    #idxToName[1] = 'None'
    idx = 1
    for line in lines:
        nameToIdx[line.strip()] = idx
        idxToName[idx] = line.strip()
        idx += 1
    return nameToIdx, idxToName


# In[115]:


def write_test_res(data, actual_sent, actual_data, preds, outfile):
    writer = open(outfile, 'w')
    for i in range(0, len(data)):
        writer.write('Sentence= ' + actual_sent[i])
        writer.write('\n')
        writer.write('Actual= '+ actual_data[i])
        writer.write('\n')
        pred_triples, _ = get_pred_triples(preds[0][i], preds[1][i], preds[2][i], preds[3][i], preds[4][i], preds[5][i], preds[6][i], data[i].SrcWords)
        pred_triples_str = []
        for pt in pred_triples:
            pred_triples_str.append(pt[0] + ' ; ' + pt[1] + ' ; ' + pt[2] + ' ; ' + pt[3] + ' ; ' + pt[4])
        writer.write('predicted:  ')
        writer.write(' | '.join(pred_triples_str) + '\n\n\n')
    writer.close()

def load_word_embedding(embed_file, vocab):
    '''
    vocab: all the uniq words present in the doc
    embed_file: pretrained word embedding path
    '''
    #print('vocab length:', len(vocab))
    custom_print('vocab length:', len(vocab))
    embed_vocab = OrderedDict()#dictionar containing all the words and word_index
    embed_matrix = list()

    embed_vocab['<PAD>'] = 0
    embed_matrix.append(np.zeros(word_embed_dim, dtype=np.float32))

    embed_vocab['<UNK>'] = 1
    embed_matrix.append(np.random.uniform(-0.25, 0.25, word_embed_dim))

    word_idx = 2
    with open(embed_file, "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) < word_embed_dim + 1:
                continue
            word = parts[0]
            if word in vocab and vocab[word] >= word_min_freq:
                vec = [np.float32(val) for val in parts[1:]]
                embed_matrix.append(vec)
                embed_vocab[word] = word_idx
                word_idx += 1

    for word in vocab:
        if word not in embed_vocab and vocab[word] >= word_min_freq:
            embed_matrix.append(np.random.uniform(-0.25, 0.25, word_embed_dim))
            embed_vocab[word] = word_idx
            word_idx += 1

    #print('embed dictionary length:', len(embed_vocab))
    custom_print('embed dictionary length:', len(embed_vocab))
    return embed_vocab, np.array(embed_matrix, dtype=np.float32)

def build_vocab(tr_data, dv_data, ts_data, save_vocab, embedding_file):
    vocab = OrderedDict()
    char_v = OrderedDict()
    char_v['<PAD>'] = 0
    char_v['<UNK>'] = 1
    char_idx = 2
    for d in tr_data:
        for word in d.SrcWords:
            if word not in vocab:
                vocab[word] = 1
            else:
                vocab[word] += 1

            for c in word:
                if c not in char_v:
                    char_v[c] = char_idx
                    char_idx += 1

    for d in dv_data + ts_data:
        for word in d.SrcWords:
            if word not in vocab:
                vocab[word] = 0

            for c in word:
                if c not in char_v:
                    char_v[c] = char_idx
                    char_idx += 1

    word_v, embed_matrix = load_word_embedding(embedding_file, vocab)
    output = open(save_vocab, 'wb')
    pickle.dump([word_v, char_v, pos_vocab, ent_vocab, dep_vocab], output)
    output.close()
    return word_v, char_v, embed_matrix

def build_tags(file1, file2, file3):
    lines = open(file1).readlines() + open(file2).readlines() + open(file3).readlines()
    pos_vocab = OrderedDict()
    pos_vocab['<PAD>'] = 0
    pos_vocab['<UNK>'] = 1
    k = 2
    for line in lines:
        line = line.strip()
        tags = line.split(' ')
        for tag in tags:
            if tag not in pos_vocab:
                pos_vocab[tag] = k
                k += 1
    return pos_vocab


def load_vocab(vocab_file):
    with open(vocab_file, 'rb') as f:
        embed_vocab, char_vocab, pos_vocab, ent_vocab, dep_vocab = pickle.load(f)
    return embed_vocab, char_vocab, pos_vocab, ent_vocab, dep_vocab



def get_max_len(sample_batch):
    src_max_len = len(sample_batch[0].SrcWords)
    for idx in range(1, len(sample_batch)):
        if len(sample_batch[idx].SrcWords) > src_max_len:
            src_max_len = len(sample_batch[idx].SrcWords)

    trg_max_len = len(sample_batch[0].TrgRels)
    for idx in range(1, len(sample_batch)):
        if len(sample_batch[idx].TrgRels) > trg_max_len:
            trg_max_len = len(sample_batch[idx].TrgRels)

    return src_max_len, trg_max_len

def get_words_index_seq(words, max_len):
    toks = ['[CLS]'] + [wd for wd in words] + ['[SEP]'] + ['[PAD]' for i in range(max_len-len(words))]
    bert_ids = bert_tokenizer.convert_tokens_to_ids(toks)
    bert_mask = [1 for idx in range(len(words) + 2)] + [0 for idx in range(max_len - len(words))]
    return bert_ids, bert_mask

# In[128]:


def get_pos_tag_index_seq(pos_seq, max_len):
    seq = list()
    for t in pos_seq:
        if t in pos_vocab:
            seq.append(pos_vocab[t])
        else:
            seq.append(pos_vocab['<UNK>'])
    pad_len = max_len - len(seq)
    for i in range(0, pad_len):
        seq.append(pos_vocab['<PAD>'])
    return seq


def get_ent_tag_index_seq(ent_seq, max_len):
    seq = list()
    for t in ent_seq:
        if t in ent_vocab:
            seq.append(ent_vocab[t])
        else:
            seq.append(ent_vocab['<UNK>'])
    pad_len = max_len - len(seq)
    for i in range(0, pad_len):
        seq.append(ent_vocab['<PAD>'])
    return seq


def get_dep_tag_index_seq(dep_seq, max_len):
    seq = list()
    for t in dep_seq:
        if t in dep_vocab:
            seq.append(dep_vocab[t])
        else:
            seq.append(dep_vocab['<UNK>'])
    pad_len = max_len - len(seq)
    for i in range(0, pad_len):
        seq.append(dep_vocab['<PAD>'])
    return seq

# In[129]:


def get_padded_mask(cur_len, max_len):
    mask_seq = list()
    for i in range(0, cur_len):
        mask_seq.append(0)
    pad_len = max_len - cur_len
    for i in range(0, pad_len):
        mask_seq.append(1)
    return mask_seq


# In[130]:


def get_char_seq(words, max_len):
    char_seq = list()
    for i in range(0, conv_filter_size - 1):
        char_seq.append(char_vocab['<PAD>'])
    for word in words:
        for c in word[0:min(len(word), max_word_len)]:
            if c in char_vocab:
                char_seq.append(char_vocab[c])
            else:
                char_seq.append(char_vocab['<UNK>'])
        pad_len = max_word_len - len(word)
        for i in range(0, pad_len):
            char_seq.append(char_vocab['<PAD>'])
        for i in range(0, conv_filter_size - 1):
            char_seq.append(char_vocab['<PAD>'])

    pad_len = max_len - len(words)
    for i in range(0, pad_len):
        for i in range(0, max_word_len + conv_filter_size - 1):
            char_seq.append(char_vocab['<PAD>'])
    return char_seq


# In[131]:


#[1,7,3,10,-1,-1,-1,...]
def get_padded_pointers_trig(pointers, pidx, max_len):
    idx_list = []
    for p in pointers:
        idx_list.append(p[pidx])
    idx_list.append(0)
    pad_len = max_len - len(pointers)
    for i in range(0, pad_len):
        idx_list.append(-1)
    return idx_list



#[1,7,3,10,-1,-1,-1,...]
def get_padded_pointers_arg(pointers, pidx, max_len):
    idx_list = []
    for p in pointers:
        idx_list.append(p[pidx])
    idx_list.append(1)
    pad_len = max_len - len(pointers)
    for i in range(0, pad_len):
        idx_list.append(-1)
    return idx_list


# In[132]:


#[1,2,3,4,0,0,0,...]
def get_positional_index(sent_len, max_len):
    index_seq = [min(i + 1, max_positional_idx - 1) for i in range(sent_len)]
    index_seq += [0 for i in range(max_len - sent_len)]
    return index_seq


# In[133]:


#[5,2,19,23,'None',<pad>,<pad>,<pad>,...]
def get_padded_relations(rels, max_len):
    rel_list = []
    for r in rels:
        rel_list.append(r)
    rel_list.append(relnameToIdx['NA'])
    pad_len = max_len + 1 - len(rel_list)
    for i in range(0, pad_len):
        rel_list.append(relnameToIdx['<PAD>'])
    return rel_list


# In[134]:


#[5,2,19,23,'None',<pad>,<pad>,<pad>,...]
def get_padded_events(events, max_len):
    event_list = []
    for r in events:
        event_list.append(r)
    #event_list.append(eventnameToIdx['None'])
    pad_len = max_len + 1 - len(event_list)
    for i in range(0, pad_len):
        event_list.append(eventnameToIdx['<PAD>'])
    return event_list


# In[135]:


#[5,2,19,23,'None',<pad>,<pad>,<pad>,...]
def get_padded_args(args, max_len):
    arg_list = []
    for r in args:
        arg_list.append(r)
    arg_list.append(argnameToIdx['NA'])
    pad_len = max_len + 1 - len(arg_list)
    for i in range(0, pad_len):
        arg_list.append(argnameToIdx['<PAD>'])
    return arg_list


# In[136]:


#[5,2,19,23,'None',<pad>,<pad>,<pad>,...]
def get_relation_index_seq(rel_ids, max_len):
    seq = list()
    # seq.append(relnameToIdx['<SOS>'])
    for r in rel_ids:
        seq.append(r)
    seq.append(relnameToIdx['NA'])
    pad_len = max_len + 1 - len(seq)
    for i in range(0, pad_len):
        seq.append(relnameToIdx['<PAD>'])
    return seq


# In[137]:


def get_entity_masks(pointers, src_max, trg_max):
    arg1_masks = []#
    arg2_masks = []#
    for p in pointers:#for each record in a sentence
        arg1_mask = [1 for i in range(src_max)]#list of size max_src_len [1, 1, 1, 1,...]
        arg1_mask[p[0]] = 0#set the value of word_pos_index of the first word of entity_1=0 [1, 1, 1, 0, 1, 1,...]
        arg1_mask[p[1]] = 0#set the value of word_pos_index of the last word of entity_1=0 [1, 1, 1, 0, 1, 1, 0, 1, 1,...]

        arg2_mask = [1 for i in range(src_max)]#list of size max_src_len [1, 1, 1,...]
        arg2_mask[p[2]] = 0#set the value of word_pos_index of the first word of entity_1=0
        arg2_mask[p[3]] = 0#set the value of word_pos_index of the last word of entity_2=0

        arg1_masks.append(arg1_mask)
        arg2_masks.append(arg2_mask)

    pad_len = trg_max + 1 -len(pointers)
    for i in range(0, pad_len):
        arg1_mask = [1 for i in range(src_max)]
        arg2_mask = [1 for i in range(src_max)]
        arg1_masks.append(arg1_mask)
        arg2_masks.append(arg2_mask)
    return arg1_masks, arg2_masks #list of length max_trg_len where each item is list of size max_src_len. Each item of that list is mask where all but start and end index of entity_1 and entity_2 set to 1 respectively.


# In[138]:


def get_batch_data(cur_samples, is_training=False):
    """
    Returns the training samples and labels as numpy array
    """
    batch_src_max_len, batch_trg_max_len = get_max_len(cur_samples)#call get_max_len(): find the max length of src and target per batch
    batch_trg_max_len += 1#may be EOS relation
    #print('max_src_len_batch={}'.format(batch_src_max_len))
    #print('max_trg_len_batch={}'.format(batch_trg_max_len))
    src_words_list = list()#each element is a list of word indices present in a sentence
    bert_mask_list = list()
    src_words_mask_list = list()#each element is a list of mask value, 0 if actual word and 1 if padded word
    src_char_seq = list()#each element is a charater idex sequence per sentence
    decoder_input_list = list()
    #adj_lst = []
    positional_index_list = []#each element is a sequence of positional index of the words in a sentence
    src_pos_tag_seq = list()#pos tag
    src_ent_tag_seq = list()#ent tag
    src_dep_tag_seq = list()#dep tag

    rel_seq = list()
    event_seq=list()#******
    arg_seq=list()#********
    trigger_start_seq = list()
    trigger_end_seq = list()
    entity_start_seq = list()
    entity_end_seq = list()
    trigger_mask_seq = []
    entity_mask_seq = []
    '''all commmnets in the following are about the 'items' appended to that respective lists'''
    for sample in cur_samples:
        bert_ids, bert_mask = get_words_index_seq(sample.SrcWords, batch_src_max_len)
        src_words_list.append(bert_ids)#call get_words_index_seq():[list of word_index of length max_src_len]
        bert_mask_list.append(bert_mask)
        src_words_mask_list.append(get_padded_mask(sample.SrcLen, batch_src_max_len))#call get_padded_mask(): [0,0,0..till srclength,1,1,1,...till padded length]
        src_char_seq.append(get_char_seq(sample.SrcWords, batch_src_max_len))#call get_char_seq(): [character index sequence with padded for CNN processing]
        #cur_masked_adj = np.zeros((batch_src_max_len, batch_src_max_len), dtype=np.float32)#skip
        #cur_masked_adj[:len(sample.SrcWords), :len(sample.SrcWords)] = sample.AdjMat#skip
        #adj_lst.append(cur_masked_adj)#skip
        positional_index_list.append(get_positional_index(len(sample.SrcWords), batch_src_max_len))#positional index of each word in the source sentence padded with 0
        src_pos_tag_seq.append(get_pos_tag_index_seq(sample.PosTags, batch_src_max_len))#each element is [list of tag index of each word in the sentence of length max_src_len]
        src_ent_tag_seq.append(get_ent_tag_index_seq(sample.EntTags, batch_src_max_len))######
        src_dep_tag_seq.append(get_dep_tag_index_seq(sample.DepTags, batch_src_max_len))######
        if is_training:
            trigger_start_seq.append(get_padded_pointers_trig(sample.TrgPointers, 0, batch_trg_max_len))#list of all the start index of the tuple's event in a sentence with padding -1 (to max_trg_len)
            trigger_end_seq.append(get_padded_pointers_trig(sample.TrgPointers, 1, batch_trg_max_len))#list of all the end index of the tuple's event in a sentence with pad -1 (to max_trg_len)
            entity_start_seq.append(get_padded_pointers_arg(sample.TrgPointers, 2, batch_trg_max_len))#list of all the first index of the tuple's argument in a sequence with pad -1(to max_trg_len)
            entity_end_seq.append(get_padded_pointers_arg(sample.TrgPointers, 3, batch_trg_max_len))#list of all the end index of the tuple's argument in a sentence with pad -1(to max_trg_len)
            rel_seq.append(get_padded_relations(sample.TrgRels, batch_trg_max_len))#list of all the relation index(from rel_vocab) padded with 'NA' and '<Pad>'

            event_seq.append(get_padded_events(sample.eventTypes, batch_trg_max_len))#list of all the event index(from event_vocab) padded with <Pad>'
            arg_seq.append(get_padded_args(sample.argTypes, batch_trg_max_len))#list of all the event index(from event_vocab) padded with 'NA' and '<Pad>'

            decoder_input_list.append(get_relation_index_seq(sample.TrgRels, batch_trg_max_len))#list of all the relation index(from rel_vocab) padded with 'None' and '<Pad>'

            trigger_mask, entity_mask = get_entity_masks(sample.TrgPointers, batch_src_max_len, batch_trg_max_len)#list of length max_trg_len where each item is a list of size max_src_len. Each item of that list is mask where all but start and end index of entity_1 (and entity_2) set to 1 (respectively).
            trigger_mask_seq.append(trigger_mask)
            entity_mask_seq.append(entity_mask)
        else:
            decoder_input_list.append(get_relation_index_seq([], 1))

    return {'src_words': np.array(src_words_list, dtype=np.float32),#list of word_index
            'bert_mask': np.array(bert_mask_list),
            'pos_tag_seq': np.array(src_pos_tag_seq),#list of pos tag index
            'ent_tag_seq': np.array(src_ent_tag_seq),#list of ent tag index (pad, unk, 0, 1)
            'dep_tag_seq': np.array(src_dep_tag_seq),
            'positional_seq': np.array(positional_index_list),#list of word_position_index
            'src_words_mask': np.array(src_words_mask_list),#list of source word masks [0,0,0,1,1]
            'src_chars': np.array(src_char_seq),#list of source character sequences with padding for CNN operation
            'decoder_input': np.array(decoder_input_list),#list of all the relation indexes present in the trg_seq padded till amx_trg_len(for training), [] for testing
            'event': np.array(event_seq),
            'arg': np.array(arg_seq),
            'rel': np.array(rel_seq),#list of relation seq padded till max_trg_len
            'trigger_start':np.array(trigger_start_seq),#list of all the start index of the first entities (present in the trg_seq of len max_trg_len) padded with -1
            'trigger_end': np.array(trigger_end_seq),#list of all the last index of the first entities (present in the trg_seq of len max_trg_len) padded with -1
            'entity_start': np.array(entity_start_seq),#list of all the start index of the second entities (present in the trg_seq of len max_trg_len) padded with -1
            'entity_end': np.array(entity_end_seq),#list of all the last index of the second entities (present in the trg_seq of len max_trg_len) padded with -1
            'trigger_mask': np.array(trigger_mask_seq),#list of entity_1 mask, it's a list of size max_trg_len. and each item  is a list of size max_src_len, alll 1 but the entity_1's start and end pos is 0.
            'entity_mask': np.array(entity_mask_seq)}#list of entity_2 mask,...

class WordEmbeddings(nn.Module):
    def __init__(self, vocab_size, embed_dim, pre_trained_embed_matrix, drop_out_rate):
        super(WordEmbeddings, self).__init__()
        self.embeddings = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.embeddings.weight.data.copy_(torch.from_numpy(pre_trained_embed_matrix))
        self.dropout = nn.Dropout(drop_out_rate)

    def forward(self, words_seq):
        word_embeds = self.embeddings(words_seq)
        word_embeds = self.dropout(word_embeds)
        return word_embeds

    def weight(self):
        return self.embeddings.weight


# In[140]:


class CharEmbeddings(nn.Module):
    def __init__(self, vocab_size, embed_dim, drop_out_rate):
        super(CharEmbeddings, self).__init__()
        self.embeddings = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.dropout = nn.Dropout(drop_out_rate)

    def forward(self, words_seq):
        char_embeds = self.embeddings(words_seq)
        char_embeds = self.dropout(char_embeds)
        return char_embeds


# In[141]:


class POSEmbeddings(nn.Module):
    def __init__(self, tag_len, tag_dim, drop_out_rate):
        super(POSEmbeddings, self).__init__()
        self.embeddings = nn.Embedding(tag_len, tag_dim, padding_idx=0)
        self.dropout = nn.Dropout(drop_out_rate)

    def forward(self, pos_seq):
        pos_embeds = self.embeddings(pos_seq)
        pos_embeds = self.dropout(pos_embeds)
        return pos_embeds

class ENTEmbeddings(nn.Module):
    def __init__(self, tag_len, tag_dim, drop_out_rate):
        super(ENTEmbeddings, self).__init__()
        self.embeddings = nn.Embedding(tag_len, tag_dim, padding_idx=0)
        self.dropout = nn.Dropout(drop_out_rate)

    def forward(self, ent_seq):
        ent_embeds = self.embeddings(ent_seq)
        ent_embeds = self.dropout(ent_embeds)
        return ent_embeds


class DEPEmbeddings(nn.Module):
    def __init__(self, tag_len, tag_dim, drop_out_rate):
        super(DEPEmbeddings, self).__init__()
        self.embeddings = nn.Embedding(tag_len, tag_dim, padding_idx=0)
        self.dropout = nn.Dropout(drop_out_rate)

    def forward(self, dep_seq):
        dep_embeds = self.embeddings(dep_seq)
        dep_embeds = self.dropout(dep_embeds)
        return dep_embeds


class Attention(nn.Module):
    def __init__(self, input_dim):
        super(Attention, self).__init__()
        self.input_dim = input_dim#300
        self.linear_ctx = nn.Linear(self.input_dim, self.input_dim, bias=False)
        self.linear_query = nn.Linear(self.input_dim, self.input_dim, bias=True)
        self.v = nn.Linear(self.input_dim, 1)

    def forward(self, s_prev, enc_hs, src_mask):
        uh = self.linear_ctx(enc_hs)
        wq = self.linear_query(s_prev)
        wquh = torch.tanh(wq + uh)
        attn_weights = self.v(wquh).squeeze()
        attn_weights.data.masked_fill_(src_mask.data, -float('inf'))
        attn_weights = F.softmax(attn_weights, dim=-1)
        ctx = torch.bmm(attn_weights.unsqueeze(1), enc_hs).squeeze()
        return ctx, attn_weights


# In[143]:




class BERT(nn.Module):
    def __init__(self, drop_out_rate):
        super(BERT, self).__init__()
        self.bert = BertModel.from_pretrained(bert_model_name)
        if not update_bert:
            for param in self.bert.parameters():
                param.requires_grad = False
        self.dropout = nn.Dropout(drop_out_rate)

    def forward(self, input_ids, bert_mask, is_training=False):
        seq_out = self.bert(input_ids, attention_mask=bert_mask)
        seq_out = seq_out[0][:, 1:-1, :]
        # seq_out = self.dropout(seq_out)
        return seq_out

class Encoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, layers, is_bidirectional, drop_out_rate):
        super(Encoder, self).__init__()
        self.input_dim = input_dim#768+char_emb+pos_emb
        self.hidden_dim = hidden_dim#150
        self.layers = layers#1
        self.is_bidirectional = is_bidirectional#True
        self.drop_rate = drop_out_rate#0.3
        self.bert_vec = BERT(drop_out_rate)
        #self.word_embeddings = WordEmbeddings(len(word_vocab), word_embed_dim, word_embed_matrix, drop_rate)
        self.pos_embeddings = POSEmbeddings(len(pos_vocab), pos_embed_dim, drop_rate)
        self.ent_embeddings = ENTEmbeddings(len(ent_vocab), ent_emb_size, drop_rate)
        self.dep_embeddings = DEPEmbeddings(len(dep_vocab), dep_embed_dim, drop_rate)
        self.char_embeddings = CharEmbeddings(len(char_vocab), char_embed_dim, drop_rate)
        # self.pos_embeddings = nn.Embedding(max_positional_idx, positional_embed_dim, padding_idx=0)
        if enc_type == 'LSTM':
            self.lstm = nn.LSTM(self.input_dim, self.hidden_dim, self.layers, batch_first=True,
                                bidirectional=self.is_bidirectional, dropout=drop_out_rate)
        '''
        elif enc_type == 'GCN':
            self.reduce_dim = nn.Linear(self.input_dim, 2 * self.hidden_dim)
            self.gcn = GCN(gcn_num_layers, 2* self.hidden_dim, 2 * self.hidden_dim)

        else:
            self.lstm = nn.LSTM(self.input_dim, self.hidden_dim, self.layers, batch_first=True,
                                bidirectional=self.is_bidirectional)
            self.gcn = GCN(gcn_num_layers, 2 * self.hidden_dim, 2 * self.hidden_dim)
        '''

        self.dropout = nn.Dropout(self.drop_rate)
        self.conv1d = nn.Conv1d(char_embed_dim, char_feature_size, conv_filter_size)
        self.max_pool = nn.MaxPool1d(max_word_len + conv_filter_size - 1, max_word_len + conv_filter_size - 1)
        # self.mhc = 3
        # self.mha = Multi_Head_Self_Attention(self.mhc, 2 * self.hidden_dim)

    def forward(self, words, bert_mask, pos_tag_seq, ent_tag_seq, dep_tag_seq, chars, pos_seq, is_training=False):
        bert_embeds = self.bert_vec(words, bert_mask, is_training)
        word_input = bert_embeds
        #src_word_embeds = self.word_embeddings(words)#[bs, max_seq_len, emb_dim]
        #custom_print(word_input.shape)
        pos_embeds = self.pos_embeddings(pos_tag_seq)
        ent_embeds = self.ent_embeddings(ent_tag_seq)
        dep_embeds = self.dep_embeddings(dep_tag_seq)
        #custom_print(pos_embeds.shape)
        # pos_embeds = self.dropout(self.pos_embeddings(pos_seq))
        char_embeds = self.char_embeddings(chars)#[]
        char_embeds = char_embeds.permute(0, 2, 1)#[bs, emb_dim, max_seq_len]

        char_feature = torch.tanh(self.max_pool(self.conv1d(char_embeds)))
        char_feature = char_feature.permute(0, 2, 1)
        #custom_print(char_feature.shape)

        #words_input = torch.cat((word_input, pos_embeds, ent_embeds, dep_embeds, char_feature), -1)#[bs, max_seq_len, emb_dim=350]
        words_input = torch.cat((word_input, pos_embeds, ent_embeds, dep_embeds), -1)#[bs, max_seq_len, emb_dim=350]

        #custom_print(words_input.shape)

        if enc_type == 'LSTM':
            outputs, hc = self.lstm(words_input)
        '''
        elif enc_type == 'GCN':
            outputs = self.reduce_dim(words_input)
            outputs = self.gcn(outputs, adj)
        else:
            outputs, hc = self.lstm(words_input)
            outputs = self.dropout(outputs)
            outputs = self.gcn(outputs, adj)
        '''
        # outputs += pos_embeds
        # outputs = self.mha(outputs, outputs, outputs)
        #outputs = self.dropout(outputs)#(bs, seq_len, hid_dim)
        outputs = self.dropout(words_input)#(bs, seq_len, hid_dim)
        #custom_print(outputs.shape)
        return outputs

class Decoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, layers, drop_out_rate, max_length):
        super(Decoder, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.layers = layers
        self.drop_rate = drop_out_rate
        self.max_length = max_length

        if att_type == 0:
            self.attention = Attention(input_dim)
            self.lstm = nn.LSTMCell(10 * self.input_dim, self.hidden_dim)
        elif att_type == 1:
            # self.w = nn.Linear(9 * self.input_dim, self.input_dim)
            self.attention = Attention(input_dim)
            self.lstm = nn.LSTMCell(10 * self.input_dim, self.hidden_dim)
        else:
            # self.w = nn.Linear(9 * self.input_dim, self.input_dim)
            self.attention1 = Attention(input_dim)
            self.attention2 = Attention(input_dim)
            self.lstm = nn.LSTMCell(11 * self.input_dim, self.hidden_dim)

        self.trig_pointer_lstm = nn.LSTM(2 * self.input_dim, self.input_dim, 1, batch_first=True,
                                       bidirectional=True)
        self.ent_pointer_lstm = nn.LSTM(4 * self.input_dim, self.input_dim, 1, batch_first=True,
                                       bidirectional=True)

        #self.arg1s_lin = nn.Linear(2 * self.input_dim, 1)#trigger_s
        self.trigger_s_lin = nn.Linear(2 * self.input_dim, 1)
        #self.arg1e_lin = nn.Linear(2 * self.input_dim, 1)#trigger_e
        self.trigger_e_lin = nn.Linear(2 * self.input_dim, 1)
        #self.arg2s_lin = nn.Linear(2 * self.input_dim, 1)#entity_s
        self.entity_s_lin = nn.Linear(2 * self.input_dim, 1)
        #self.arg2e_lin = nn.Linear(2 * self.input_dim, 1)#entity_e
        self.entity_e_lin = nn.Linear(2 * self.input_dim, 1)


        self.et_lin = nn.Linear(5* self.input_dim, len(eventnameToIdx))#***************to identify the event type
        self.argt_lin = nn.Linear(9* self.input_dim + len(eventnameToIdx), len(argnameToIdx))#***************to identify the argumwnt type

        self.rel_lin = nn.Linear(9 * self.input_dim + len(eventnameToIdx) , len(relnameToIdx))#to identify the role
        #self.rel_lin = nn.Linear(9 * self.input_dim + len(eventnameToIdx), len(relnameToIdx))#to identify the role

        self.dropout = nn.Dropout(self.drop_rate)
        self.w = nn.Linear(9 * self.input_dim, self.input_dim)

    def forward(self, y_prev, prev_tuples, h_prev, enc_hs, src_mask, trigger, entity, trigger_mask, entity_mask,
                is_training=False):

        '''
        y_prev= [bs, dec_hid_dim]
        prev_tuples=[bs, 9*dec_hid_dim]
        h_prev=([bs,dec_hid_dim],[bs,dec_hid_dim])
        enc_hs=[bs,seq_len,dec_hid_dim]
        src_mask=[bs,seq_len]
        trigger=[bs,4*dec_hid_dim]
        entity=[bs,4*dec_hid_dim]
        trigger_mask=[bs, seq_len]
        entity_mask=[bs, seq_len]
        '''
        src_time_steps = enc_hs.size()[1]

        if att_type == 0:#not used
            ctx, attn_weights = self.attention(h_prev[0].squeeze().unsqueeze(1).repeat(1, src_time_steps, 1),
                                                enc_hs, src_mask)
        elif att_type == 1:#not used
            reduce_prev_tuples = self.w(prev_tuples)
            ctx, attn_weights = self.attention(reduce_prev_tuples.unsqueeze(1).repeat(1, src_time_steps, 1),
                                                enc_hs, src_mask)
        else:
            ctx1, attn_weights1 = self.attention1(h_prev[0].squeeze().unsqueeze(1).repeat(1, src_time_steps, 1),
                                               enc_hs, src_mask)
            reduce_prev_tuples = self.w(prev_tuples)
            ctx2, attn_weights2 = self.attention2(reduce_prev_tuples.unsqueeze(1).repeat(1, src_time_steps, 1),
                                               enc_hs, src_mask)
            ctx = torch.cat((ctx1, ctx2), -1)#[bs,2*300]
            attn_weights = (attn_weights1 + attn_weights2) / 2#[bs,src_seq_len]

        s_cur = torch.cat((prev_tuples, ctx), 1)#[bs, 11*300]
        hidden, cell_state = self.lstm(s_cur, h_prev)
        hidden = self.dropout(hidden)#[bs, 300]

        if use_hadamard:
            enc_hs = enc_hs * attn_weights.unsqueeze(2)

        trig_pointer_lstm_input = torch.cat((enc_hs, hidden.unsqueeze(1).repeat(1, src_time_steps, 1)), 2)#[bs, src_seq_len, 2*300]
        trig_pointer_lstm_out, phc = self.trig_pointer_lstm(trig_pointer_lstm_input)
        trig_pointer_lstm_out = self.dropout(trig_pointer_lstm_out)#[bs, src_seq_len, 2*300]

        ent_pointer_lstm_input = torch.cat((trig_pointer_lstm_input, trig_pointer_lstm_out), 2)#[bs,src_seq_len, 4*300]
        ent_pointer_lstm_out, phc = self.ent_pointer_lstm(ent_pointer_lstm_input)#
        ent_pointer_lstm_out = self.dropout(ent_pointer_lstm_out)#[bs, src_seq_len, 2*300]

        trig_s = self.trigger_s_lin(trig_pointer_lstm_out).squeeze()#[bs,src_seq_len]
        trig_s.data.masked_fill_(src_mask.data, -float('inf'))

        trig_e = self.trigger_e_lin(trig_pointer_lstm_out).squeeze()#[bs,src_seq_len]
        trig_e.data.masked_fill_(src_mask.data, -float('inf'))

        ent_s = self.entity_s_lin(ent_pointer_lstm_out).squeeze()#[bs,src_seq_len]
        ent_s.data.masked_fill_(src_mask.data, -float('inf'))

        ent_e = self.entity_e_lin(ent_pointer_lstm_out).squeeze()
        ent_e.data.masked_fill_(src_mask.data, -float('inf'))#[bs,src_seq_len]

        trig_s_weights = F.softmax(trig_s, dim=-1)#normaized probability of each word index to be the strat index of arg1
        trig_e_weights = F.softmax(trig_e, dim=-1)#normaized probability of each word index to be the end index of arg1

        trig_sv = torch.bmm(trig_e_weights.unsqueeze(1), trig_pointer_lstm_out).squeeze()#[bs,2*300]
        trig_ev = torch.bmm(trig_s_weights.unsqueeze(1), trig_pointer_lstm_out).squeeze()#[bs, 2*300]
        trig_et = self.dropout(torch.cat((trig_sv, trig_ev), -1))#[bs,4*300]#holds trigger and event type representation

        ent_s_weights = F.softmax(ent_s, dim=-1)
        ent_e_weights = F.softmax(ent_e, dim=-1)

        ent_sv = torch.bmm(ent_e_weights.unsqueeze(1), ent_pointer_lstm_out).squeeze()#[bs, 2*300]
        ent_ev = torch.bmm(ent_s_weights.unsqueeze(1), ent_pointer_lstm_out).squeeze()#[bs, 2*300]
        ent_argt = self.dropout(torch.cat((ent_sv, ent_ev), -1))#[bs,4*300]

        # enc_hs = self.mha(enc_hs, enc_hs, enc_hs)
        # sent1 = self.mha1(enc_hs, arg1, src_mask)
        # sent2 = self.mha2(enc_hs, arg2, src_mask)

        # if is_training:
        #     # arg1 = self.dropout(multi_head_pooling(mh_hid, arg1_mask, 'sum'))
        #     # arg2 = self.dropout(multi_head_pooling(mh_hid, arg2_mask, 'sum'))
        #
        #     # src_mask = src_mask + arg1_mask.eq(0) + arg2_mask.eq(0)
        #     # src_mask = src_mask.eq(0).eq(0)
        #     sent = self.dropout(multi_head_pooling(mh_hid, src_mask, 'max'))
        # else:
        #     arg1_one_hot = F.gumbel_softmax(arg1s).byte() + F.gumbel_softmax(arg1e).byte()
        #     arg2_one_hot = F.gumbel_softmax(arg2s).byte() + F.gumbel_softmax(arg2e).byte()
        #     # arg1_mask = arg1_one_hot.eq(0)
        #     # arg2_mask = arg2_one_hot.eq(0)
        #
        #     # arg1 = self.dropout(multi_head_pooling(mh_hid, arg1_mask, 'sum'))
        #     # arg2 = self.dropout(multi_head_pooling(mh_hid, arg2_mask, 'sum'))
        #
        #     # src_mask = src_mask + arg1_one_hot + arg2_one_hot
        #     # src_mask = src_mask.eq(0).eq(0)
        #     sent = self.dropout(multi_head_pooling(mh_hid, src_mask, 'max'))


        event_types = self.et_lin(torch.cat((trig_et, hidden),-1))#[bs, 5*300]--->[bs, 33]
        #custom_print('event_types size={}'.format(event_types.shape))
        arg_types = self.argt_lin(torch.cat((trig_et, ent_argt, event_types, hidden), -1))#[bs, 9*300]----> [bs, 7]
        #custom_print('arg_types size={}'.format(arg_types.shape))
        rel = self.rel_lin(torch.cat((trig_et, ent_argt, event_types, hidden), -1))#[bs,9*300]---->[bs, 36]
        #custom_print('rel size={}'.format(rel.shape))

        if is_training:
            trig_s = F.log_softmax(trig_s, dim=-1)#[bs,max_src_len]
            trig_e = F.log_softmax(trig_e, dim=-1)#[bs,max_src_len]
            ent_s = F.log_softmax(ent_s, dim=-1)#[bs,max_src_len]
            ent_e = F.log_softmax(ent_e, dim=-1)#[bs,max_src_len]
            rel = F.log_softmax(rel, dim=-1)#[bs,max_rel_types]
            event_types=F.log_softmax(event_types, dim=-1)#[bs, no_event_types]
            arg_types=F.log_softmax(arg_types, dim=-1)#[bs, no_arg_types]

            return rel.unsqueeze(1), trig_s.unsqueeze(1), trig_e.unsqueeze(1), ent_s.unsqueeze(1),  ent_e.unsqueeze(1), (hidden, cell_state), trig_et, ent_argt, event_types.unsqueeze(1), arg_types.unsqueeze(1)
        else:
            trig_s = F.softmax(trig_s, dim=-1)
            trig_e = F.softmax(trig_e, dim=-1)
            ent_s = F.softmax(ent_s, dim=-1)
            ent_e = F.softmax(ent_e, dim=-1)
            rel = F.log_softmax(rel, dim=-1)
            event_types=F.log_softmax(event_types, dim=-1)#[bs, no_event_types]
            arg_types=F.log_softmax(arg_types, dim=-1)#[bs, no_arg_types]
            return rel.unsqueeze(1), trig_s.unsqueeze(1), trig_e.unsqueeze(1), ent_s.unsqueeze(1), ent_e.unsqueeze(1), (hidden, cell_state), trig_et, ent_argt, event_types.unsqueeze(1), arg_types.unsqueeze(1)

class Seq2SeqModel(nn.Module):
    def __init__(self):
        super(Seq2SeqModel, self).__init__()
        self.encoder = Encoder(enc_inp_size, int(enc_hidden_size/2), 1, True, drop_rate)
        self.decoder = Decoder(dec_inp_size, dec_hidden_size, 1, drop_rate, max_trg_len)
        self.relation_embeddings = nn.Embedding(len(relnameToIdx), word_embed_dim)
        # self.w = nn.Linear(10 * dec_inp_size, dec_inp_size)
        self.dropout = nn.Dropout(drop_rate)

    def forward(self, src_words_seq, bert_mask, pos_tag_seq, ent_tag_seq, dep_tag_seq, src_mask, src_char_seq, pos_seq, trg_words_seq, trg_rel_cnt,
                trigger_mask, entity_mask, is_training=False):
        #custom_print('src_word_seq = {}'.format(src_words_seq.shape))#[32, max_seq_len]
        if is_training:
            trg_word_embeds = self.dropout(self.relation_embeddings(trg_words_seq))
        #custom_print('src_word_seq = {}'.format(src_words_seq.shape))#[32, max_seq_len]
        batch_len = src_words_seq.size()[0]#batch_size
        #custom_print('batch_size={}'.format(batch_len))
        #src_time_steps = src_words_seq.size()[1]#max_src_len in that batch
        #custom_print('max_src_len={}'.format(src_time_steps))
        time_steps = trg_rel_cnt#max_trg_len (max no of relations present in trg_seq in that batch)
        #custom_print('time_step={}'.format(time_steps))
        #print(src_words_seq.shape)
        enc_hs = self.encoder(src_words_seq, bert_mask, pos_tag_seq, ent_tag_seq, dep_tag_seq, src_char_seq, pos_seq, is_training)#call encoder(): (bs, seq_len, hid_dim)
        #custom_print(enc_hs.shape)
        src_time_steps = enc_hs.shape[1]
        #custom_print('max_src_len={}'.format(src_time_steps))
        #custom_print('encoder output dim = {}'.format(enc_hs.shape))
        #custom_print('source_mask={}'.format(src_mask.shape))
        h0 = autograd.Variable(torch.FloatTensor(torch.zeros(batch_len, dec_hidden_size))).cuda()#[bs, 300]
        c0 = autograd.Variable(torch.FloatTensor(torch.zeros(batch_len, dec_hidden_size))).cuda()#[bs, 300]
        dec_hid = (h0, c0)

        dec_inp = autograd.Variable(torch.FloatTensor(torch.zeros(batch_len, dec_hidden_size))).cuda()#[bs, 300]
        trigger = autograd.Variable(torch.FloatTensor(torch.zeros(batch_len, 4 * dec_hidden_size))).cuda()#[bs, 4*300]
        entity = autograd.Variable(torch.FloatTensor(torch.zeros(batch_len, 4 * dec_hidden_size))).cuda()#[bs, 4*300]

        prev_tuples = torch.cat((trigger, entity, dec_inp), -1)#[bs, 9*300]
        #custom_print('start decoding.....')
        if is_training:
            dec_outs = self.decoder(dec_inp, prev_tuples, dec_hid, enc_hs, src_mask, trigger, entity,
                                    trigger_mask[:, 0, :].squeeze(), entity_mask[:, 0, :].squeeze(), is_training)
        else:
            dec_outs = self.decoder(dec_inp, prev_tuples, dec_hid, enc_hs, src_mask, trigger, entity, None, None,
                                    is_training)
        rel = dec_outs[0]#[bs,1,no_of_rel_types]
        trig_s = dec_outs[1]#[bs, 1, max_src_len]
        trig_e = dec_outs[2]#[bs, 1, max_src_len]
        ent_s = dec_outs[3]#[bs, 1, max_src_len]
        ent_e = dec_outs[4]#[bs, 1, max_src_len]
        dec_hid = dec_outs[5]#([bs, hid_dim],[bs, hid_dim])
        trigger = dec_outs[6]#[bs, 4*300]
        entity = dec_outs[7]#[bs, 4*300]
        trg_type=dec_outs[8]#[bs, 1, no_eventTypes]
        arg_type=dec_outs[9]#[bs, 1, no_argTypes]

        topv, topi = rel[:, :, 1:].topk(1)#
        topi = torch.add(topi, 1)
        #custom_print('decoding continue...')
        for t in range(1, time_steps):
            #custom_print('time step: {}'.format(t))
            if is_training:
                dec_inp = trg_word_embeds[:, t - 1, :].squeeze()#[bs, 300]
                prev_tuples = torch.cat((trigger, entity, dec_inp), -1) + prev_tuples#[bs, 9*300]
                dec_outs = self.decoder(dec_inp, prev_tuples, dec_hid, enc_hs, src_mask, trigger, entity,
                                        trigger_mask[:, t, :].squeeze(), entity_mask[:, t, :].squeeze(), is_training)
            else:
                dec_inp = self.relation_embeddings(topi.squeeze().detach()).squeeze()
                prev_tuples = torch.cat((trigger, entity, dec_inp), -1) + prev_tuples
                dec_outs = self.decoder(dec_inp, prev_tuples, dec_hid, enc_hs, src_mask, trigger, entity, None, None,
                                        is_training)

            cur_rel = dec_outs[0]
            cur_trig_s = dec_outs[1]
            cur_trig_e = dec_outs[2]
            cur_ent_s = dec_outs[3]
            cur_ent_e = dec_outs[4]
            dec_hid = dec_outs[5]
            trigger = dec_outs[6]
            entity = dec_outs[7]
            cur_trg_type=dec_outs[8]
            cur_arg_type=dec_outs[9]

            rel = torch.cat((rel, cur_rel), 1)
            trig_s = torch.cat((trig_s, cur_trig_s), 1)
            trig_e = torch.cat((trig_e, cur_trig_e), 1)
            ent_s = torch.cat((ent_s, cur_ent_s), 1)
            ent_e = torch.cat((ent_e, cur_ent_e), 1)
            trg_type = torch.cat((trg_type, cur_trg_type),1)
            arg_type = torch.cat((arg_type, cur_arg_type),1)

            #topv, topi = cur_rel[:, :, 1:].topk(1)
            #topi = torch.add(topi, 1)
            rel_topv, rel_topi = cur_rel[:, :, 1:].topk(1)
            rel_topi = torch.add(rel_topi, 1)
            trg_topv, trg_topi = cur_trg_type[:, :, 1:].topk(1)
            trg_topi = torch.add(trg_topi, 1)
            arg_topv, arg_topi = cur_arg_type[:, :, 1:].topk(1)
            arg_topi = torch.add(arg_topi, 1)
        #custom_print('decoding complete')
        #custom_print('rel shape={}'.format(rel.shape))
        #custom_print('trig_s={}'.format(trig_s.shape))
        #custom_print('trig_e={}'.format(trig_e.shape))
        #custom_print('ent_s={}'.format(ent_s.shape))
        #custom_print('ent_e={}'.format(ent_e.shape))
        #custom_print('trg_type shape={}'.format(trg_type.shape))
        #custom_print('arg_type shape={}'.format(arg_type.shape))
        if is_training:
            rel = rel.view(-1, len(relnameToIdx))
            trig_s = trig_s.view(-1, src_time_steps)
            trig_e = trig_e.view(-1, src_time_steps)
            ent_s = ent_s.view(-1, src_time_steps)
            ent_e = ent_e.view(-1, src_time_steps)
            trg_type = trg_type.view(-1, len(eventnameToIdx))
            arg_type = arg_type.view(-1, len(argnameToIdx))
        #custom_print('execution complete for this batch')
        return rel, trig_s, trig_e, ent_s, ent_e, trg_type, arg_type

def get_model(model_id):
    if model_id == 1:
        return Seq2SeqModel()


# In[147]:


def shuffle_data(data):
    #print(len(data))
    custom_print(len(data))
    data.sort(key=lambda x: x.SrcLen)
    num_batch = int(len(data) / batch_size)
    rand_idx = random.sample(range(num_batch), num_batch)
    new_data = []
    for idx in rand_idx:
        new_data += data[batch_size * idx: batch_size * (idx + 1)]
    if len(new_data) < len(data):
        new_data += data[num_batch * batch_size:]
    return new_data

def predict(samples, model, model_id):
    pred_batch_size = batch_size
    batch_count = math.ceil(len(samples) / pred_batch_size)
    move_last_batch = False
    if len(samples) - batch_size * (batch_count - 1) == 1:
        move_last_batch = True
        batch_count -= 1
    rel = list()
    arg1s = list()
    arg1e = list()
    arg2s = list()
    arg2e = list()
    eType=list()
    argType=list()
    model.eval()
    #set_random_seeds(random_seed)
    torch.manual_seed(random_seed)
    start_time = datetime.datetime.now()
    for batch_idx in tqdm(range(0, batch_count)):
        batch_start = batch_idx * pred_batch_size
        batch_end = min(len(samples), batch_start + pred_batch_size)
        if batch_idx == batch_count - 1 and move_last_batch:
            batch_end = len(samples)

        cur_batch = samples[batch_start:batch_end]
        cur_samples_input = get_batch_data(cur_batch, False)

        src_words_seq = torch.from_numpy(cur_samples_input['src_words'].astype('long'))
        bert_words_mask = torch.from_numpy(cur_samples_input['bert_mask'].astype('bool'))
        src_pos_tags = torch.from_numpy(cur_samples_input['pos_tag_seq'].astype('long'))
        src_ent_tags = torch.from_numpy(cur_samples_input['ent_tag_seq'].astype('long'))##
        src_dep_tags = torch.from_numpy(cur_samples_input['dep_tag_seq'].astype('long'))##
        positional_seq = torch.from_numpy(cur_samples_input['positional_seq'].astype('long'))
        src_words_mask = torch.from_numpy(cur_samples_input['src_words_mask'].astype('uint8'))
        trg_words_seq = torch.from_numpy(cur_samples_input['decoder_input'].astype('long'))
        src_chars_seq = torch.from_numpy(cur_samples_input['src_chars'].astype('long'))
        #adj = torch.from_numpy(cur_samples_input['adj'].astype('float32'))

        if torch.cuda.is_available():
            src_words_seq = src_words_seq.cuda()
            bert_words_mask = bert_words_mask.cuda()
            src_pos_tags = src_pos_tags.cuda()
            src_ent_tags = src_ent_tags.cuda()
            src_dep_tags = src_dep_tags.cuda()
            src_words_mask = src_words_mask.cuda()
            trg_words_seq = trg_words_seq.cuda()
            src_chars_seq = src_chars_seq.cuda()
            #adj = adj.cuda()
            positional_seq = positional_seq.cuda()

        src_words_seq = autograd.Variable(src_words_seq)
        bert_words_mask = autograd.Variable(bert_words_mask)
        src_pos_tags = autograd.Variable(src_pos_tags)
        src_ent_tags = autograd.Variable(src_ent_tags)
        src_dep_tags = autograd.Variable(src_dep_tags)
        src_words_mask = autograd.Variable(src_words_mask)
        trg_words_seq = autograd.Variable(trg_words_seq)
        src_chars_seq = autograd.Variable(src_chars_seq)
        #adj = autograd.Variable(adj)
        positional_seq = autograd.Variable(positional_seq)

        with torch.no_grad():
            if model_id == 1:
                outputs = model(src_words_seq, bert_words_mask, src_pos_tags, src_ent_tags, src_dep_tags, src_words_mask, src_chars_seq, positional_seq, trg_words_seq,
                                max_trg_len, None, None, False)

        rel += list(outputs[0].data.cpu().numpy())
        arg1s += list(outputs[1].data.cpu().numpy())
        arg1e += list(outputs[2].data.cpu().numpy())
        arg2s += list(outputs[3].data.cpu().numpy())
        arg2e += list(outputs[4].data.cpu().numpy())
        eType += list(outputs[5].data.cpu().numpy())
        argType += list(outputs[6].data.cpu().numpy())
        model.zero_grad()

    end_time = datetime.datetime.now()
    #print('Prediction time:', end_time - start_time)
    custom_print('Prediction time:', end_time - start_time)
    return rel, arg1s, arg1e, arg2s, arg2e, eType, argType

def train_model(model_id, train_samples, dev_samples, best_model_file):
    train_size = len(train_samples)
    print('train_size')
    print(train_size)
    batch_count = int(math.ceil(train_size/batch_size))
    move_last_batch = False
    if len(train_samples) - batch_size * (batch_count - 1) == 1:
        move_last_batch = True
        batch_count -= 1
    #print(batch_count)
    custom_print(batch_count)
    model = get_model(model_id)#call get_model(id=1)
    pytorch_total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    #print('Parameters size:', pytorch_total_params)
    custom_print('Parameters size:', pytorch_total_params)
    #print(model)
    custom_print(model)
    if torch.cuda.is_available():
        model.cuda()
    if n_gpu > 1:
        model = torch.nn.DataParallel(model)

    rel_criterion = nn.NLLLoss(ignore_index=0)

    eType_criterion = nn.NLLLoss(ignore_index=0)#
    aType_criterion = nn.NLLLoss(ignore_index=0)#

    pointer_criterion = nn.NLLLoss(ignore_index=-1)
    #event type classification loss***********
    #arg type classification loss*************
    #print('weight factor:', wf)
    custom_print('weight factor:', wf)
    #optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=0.00001)
    if update_bert:
        optimizer = AdamW(model.parameters(), lr=1e-05, correct_bias=False)
    else:
        optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=0.00001)
    #custom_print(optimizer)
    #optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9)
    #print(optimizer)
    custom_print(optimizer)

    best_dev_acc = -1.0
    best_epoch_idx = -1
    best_epoch_seed = -1
    for epoch_idx in range(0, num_epoch):
        model.train()
        model.zero_grad()
        #print('Epoch:', epoch_idx + 1)
        custom_print('Epoch:', epoch_idx + 1)
        cur_seed = random_seed + epoch_idx + 1

        torch.manual_seed(cur_seed)
        #set_random_seeds(cur_seed)
        cur_shuffled_train_data = shuffle_data(train_samples)#shuffle training data
        start_time = datetime.datetime.now()
        train_loss_val = 0.0

        for batch_idx in tqdm(range(0, batch_count)):
            batch_start = batch_idx * batch_size
            batch_end = min(len(cur_shuffled_train_data), batch_start + batch_size)
            if batch_idx == batch_count - 1 and move_last_batch:
                batch_end = len(cur_shuffled_train_data)

            cur_batch = cur_shuffled_train_data[batch_start:batch_end]
            cur_samples_input = get_batch_data(cur_batch, True)#call get_batch_data()

            '''
            Each record of cur_samples_input{} holds
            {'src_words': np.array(src_words_list, dtype=np.float32),#list of word_index
            'positional_seq': np.array(positional_index_list),#list of word_position_index
            'src_words_mask': np.array(src_words_mask_list),#list of source word masks [0,0,0,1,1]
            'src_chars': np.array(src_char_seq),#list of source character sequences with padding for CNN operation
            'decoder_input': np.array(decoder_input_list),#list of all the relation indexes present in the trg_seq padded till amx_trg_len(for training), [] for testing
            'adj': np.array(adj_lst),
            'rel': np.array(rel_seq),#list of relation seq padded till max_trg_len
            'arg1_start':np.array(arg1_start_seq),#list of all the start index of the first entities (present in the trg_seq of len max_trg_len) padded with -1
            'arg1_end': np.array(arg1_end_seq),#list of all the last index of the first entities (present in the trg_seq of len max_trg_len) padded with -1
            'arg2_start': np.array(arg2_start_seq),#list of all the start index of the second entities (present in the trg_seq of len max_trg_len) padded with -1
            'arg2_end': np.array(arg2_end_seq),#list of all the last index of the second entities (present in the trg_seq of len max_trg_len) padded with -1
            'arg1_mask': np.array(arg1_mask_seq),#list of entity_1 mask, it's a list of size max_trg_len. and each item  is a list of size max_src_len, all 1 but the entity_1's start and end pos is 0.
            'arg2_mask': np.array(arg2_mask_seq)}#list of entity_2 mask,...
            }
            '''

            src_words_seq = torch.from_numpy(cur_samples_input['src_words'].astype('long'))#[23,45,1,56,78,..,0,0,..]
            bert_words_mask = torch.from_numpy(cur_samples_input['bert_mask'].astype('bool'))
            src_pos_tags = torch.from_numpy(cur_samples_input['pos_tag_seq'].astype('long'))##
            src_ent_tags = torch.from_numpy(cur_samples_input['ent_tag_seq'].astype('long'))##
            src_dep_tags = torch.from_numpy(cur_samples_input['dep_tag_seq'].astype('long'))###
            positional_seq = torch.from_numpy(cur_samples_input['positional_seq'].astype('long'))#[1,2,3,4,..,0,0,...]
            src_words_mask = torch.from_numpy(cur_samples_input['src_words_mask'].astype('bool'))#[0,0,0,0,0,1,1,1,..]
            trg_words_seq = torch.from_numpy(cur_samples_input['decoder_input'].astype('long'))#[2,5,1,6,id('none'),id(pad),id(pad),..]
            src_chars_seq = torch.from_numpy(cur_samples_input['src_chars'].astype('long'))#[0,0,3,4,5,0,0,12,2,3,4,0,0,....]
            et_seq=torch.from_numpy(cur_samples_input['event'])#
            arg_seq=torch.from_numpy(cur_samples_input['arg'])#
            rel = torch.from_numpy(cur_samples_input['rel'].astype('long'))#same as trg_words_seq
            trigger_s = torch.from_numpy(cur_samples_input['trigger_start'].astype('long'))#[3,3,7,-1,-1,-1,..]
            trigger_e = torch.from_numpy(cur_samples_input['trigger_end'].astype('long'))#[5,5,10,-1,-1,-1,..]
            entity_s = torch.from_numpy(cur_samples_input['entity_start'].astype('long'))#[9,9,14,-1,-1,..]
            entity_e = torch.from_numpy(cur_samples_input['entity_end'].astype('long'))#[12,12,17,-1,-1,-1,..]

            trigger_mask = torch.from_numpy(cur_samples_input['trigger_mask'].astype('uint8'))# [[0,0,1,1,1,1,1,1,..],[1,1,0,1,1,0,1,1...],[...]]
            entity_mask = torch.from_numpy(cur_samples_input['entity_mask'].astype('uint8'))# [[1,1,0,0,1,1,1,1,..],[1,1,0,1,0,1,1,1...],[...]]

            if torch.cuda.is_available():
                src_words_seq = src_words_seq.cuda()
                bert_words_mask = bert_words_mask.cuda()
                src_pos_tags = src_pos_tags.cuda()
                src_ent_tags = src_ent_tags.cuda()
                src_dep_tags = src_dep_tags.cuda()
                src_words_mask = src_words_mask.cuda()
                trg_words_seq = trg_words_seq.cuda()
                src_chars_seq = src_chars_seq.cuda()
                #adj = adj.cuda()
                positional_seq = positional_seq.cuda()

                rel = rel.cuda()
                et_seq = et_seq.cuda()
                arg_seq = arg_seq.cuda()

                trigger_s = trigger_s.cuda()
                trigger_e = trigger_e.cuda()
                entity_s = entity_s.cuda()
                entity_e = entity_e.cuda()

                trigger_mask = trigger_mask.cuda()
                entity_mask = entity_mask.cuda()

            src_words_seq = autograd.Variable(src_words_seq)
            bert_words_mask = autograd.Variable(bert_words_mask)
            src_pos_tags = autograd.Variable(src_pos_tags)
            src_ent_tags = autograd.Variable(src_ent_tags)
            src_dep_tags = autograd.Variable(src_dep_tags)
            src_words_mask = autograd.Variable(src_words_mask)
            trg_words_seq = autograd.Variable(trg_words_seq)
            src_chars_seq = autograd.Variable(src_chars_seq)
            #adj = autograd.Variable(adj)
            positional_seq = autograd.Variable(positional_seq)

            rel = autograd.Variable(rel)
            et_seq = autograd.Variable(et_seq)#
            arg_seq = autograd.Variable(arg_seq)#
            trigger_s = autograd.Variable(trigger_s)
            trigger_e = autograd.Variable(trigger_e)
            entity_s = autograd.Variable(entity_s)
            entity_e = autograd.Variable(entity_e)

            trigger_mask = autograd.Variable(trigger_mask)
            entity_mask = autograd.Variable(entity_mask)


            #print('src_words_seq = {}'.format(src_words_seq.shape))#[32,max_seq_len]
            #print('bert_words_mask = {}'.format(bert_words_mask.shape))
            #print('pos tags = {}'.format(src_pos_tags.shape))
            #print('rel = {}'.format(rel.shape))
            #print('trigger_s = {}'.format(trigger_s.shape))
            #print('source_mask={}'.format(src_words_mask.shape))

            #if model_id == 1:

            outputs = model(src_words_seq, bert_words_mask, src_pos_tags, src_ent_tags, src_dep_tags, src_words_mask, src_chars_seq, positional_seq, trg_words_seq, rel.size()[1], trigger_mask, entity_mask, True)# call seq2seqmodel()

            rel = rel.view(-1, 1).squeeze()
            arg1s = trigger_s.view(-1, 1).squeeze()
            arg1e = trigger_e.view(-1, 1).squeeze()
            arg2s = entity_s.view(-1, 1).squeeze()
            arg2e = entity_e.view(-1, 1).squeeze()
            et_seq = et_seq.view(-1, 1).squeeze()#
            arg_seq = arg_seq.view(-1, 1).squeeze()#

            loss = rel_criterion(outputs[0], rel) + eType_criterion(outputs[5], et_seq) + aType_criterion(outputs[6], arg_seq) +   wf * (pointer_criterion(outputs[1], arg1s) + pointer_criterion(outputs[2], arg1e)) +  wf * (pointer_criterion(outputs[3], arg2s) + pointer_criterion(outputs[4], arg2e))
            #loss = rel_criterion(outputs[0], rel) + eType_criterion(outputs[5], et_seq)  +   wf * (pointer_criterion(outputs[1], arg1s) + pointer_criterion(outputs[2], arg1e)) +  wf * (pointer_criterion(outputs[3], arg2s) + pointer_criterion(outputs[4], arg2e))

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
            if (batch_idx + 1) % update_freq == 0:
                optimizer.step()
                model.zero_grad()
            train_loss_val += loss.item()

        train_loss_val /= batch_count
        end_time = datetime.datetime.now()
        #print('Training loss:', train_loss_val)
        #print('Training time:', end_time - start_time)
        custom_print('Training loss:', train_loss_val)
        custom_print('Training time:', end_time - start_time)

        #print('\nDev Results\n')
        custom_print('\nDev Results\n')
        #set_random_seeds(random_seed)
        torch.manual_seed(cur_seed)#newly added

        dev_preds = predict(dev_samples, model, model_id)# call predict()

        pred_pos, gt_pos, correct_pos = get_F1(dev_samples, dev_preds)
        #print(pred_pos, '\t', gt_pos, '\t', correct_pos)
        custom_print(pred_pos, '\t', gt_pos, '\t', correct_pos)
        p = float(correct_pos) / (pred_pos + 1e-8)
        r = float(correct_pos) / (gt_pos + 1e-8)
        dev_acc = (2 * p * r) / (p + r + 1e-8)
        #print('F1:', dev_acc)
        custom_print('F1:', dev_acc)

        if dev_acc >= best_dev_acc:
            best_epoch_idx = epoch_idx + 1
            best_epoch_seed = cur_seed
            #custom_print('model saved......')
            #print('model saved......')
            custom_print('model saved......')
            best_dev_acc = dev_acc
            torch.save(model.state_dict(), best_model_file)

        #print('\n\n')
        custom_print('\n\n')
        if epoch_idx + 1 - best_epoch_idx >= early_stop_cnt:
            break

    #print('*******')
    #print('Best Epoch:', best_epoch_idx)
    #print('Best Epoch Seed:', best_epoch_seed)

    custom_print('*******')
    custom_print('Best Epoch:', best_epoch_idx)
    custom_print('Best Epoch Seed:', best_epoch_seed)


n_gpu = torch.cuda.device_count()
random_seed=1023
torch.manual_seed(random_seed)
#set_random_seeds(random_seed)
batch_size = 32
num_epoch = 100
model_name=1

logger = open('/home/alapan/joint_ee/5_10_21/files_23_12/test_23_12.log', 'w+')

bert_base_size = 768
update_bert = 0
bert_model_name = 'bert-base-cased'
bert_tokenizer = BertTokenizer.from_pretrained(bert_model_name, do_basic_tokenize=False)


max_src_len = 140#max sentence length = 135
max_trg_len = 23#max number of tuple
embedding_file = '/home/alapan/joint_ee/w2v.txt'#pretrained word embeddings file

word_min_freq = 2

char_embed_dim = 50
char_feature_size = 50
ent_emb_size=50
pos_embed_dim=50
dep_embed_dim=50

conv_filter_size = 3
max_word_len = 10

#max_positional_idx = 100
max_positional_idx = 140

#enc_inp_size = bert_base_size + pos_embed_dim + char_feature_size + ent_emb_size + dep_embed_dim
enc_inp_size = bert_base_size + pos_embed_dim + ent_emb_size + dep_embed_dim
enc_hidden_size = enc_inp_size
dec_inp_size = enc_hidden_size
dec_hidden_size = dec_inp_size
#word_embed_dim = 300
word_embed_dim = enc_inp_size
positional_embed_dim = word_embed_dim

drop_rate = 0.5
enc_type = ['LSTM', 'GCN', 'LSTM-GCN'][0]
att_type = 2
wf = 1.0
update_freq = 1
use_hadamard = False
early_stop_cnt = 7

Sample = recordclass("Sample", "Id SrcLen SrcWords PosTags EntTags DepTags TrgLen TrgRels eventTypes argTypes TrgPointers")
rel_file = '/home/alapan/joint_ee/role.txt'
relnameToIdx, relIdxToName = get_relations(rel_file)#return relation dictionary
event_file = '/home/alapan/joint_ee/event_type.txt'
eventnameToIdx, eventIdxToName=get_events(event_file)#return event dictionary
arg_file = '/home/alapan/joint_ee/ent_type.txt'
argnameToIdx, argIdxToName=get_arguments(arg_file)#return arg dictionary

custom_print(max_src_len, '\t', max_trg_len, '\t', drop_rate)
custom_print(batch_size, '\t', num_epoch)
custom_print(enc_type)
custom_print('loading data......')


src_train_file = '/home/alapan/joint_ee/5_10_21/train_bert.sent'
trg_train_file = '/home/alapan/joint_ee/5_10_21/train_bert.pointer'
pos_train_file = '/home/alapan/joint_ee/5_10_21/train_bert.pos'
ent_train_file = '/home/alapan/joint_ee/5_10_21/train_bert.ent'
dep_train_file = '/home/alapan/joint_ee/5_10_21/train_bert.dep'

train_data = read_data(src_train_file, trg_train_file, pos_train_file, ent_train_file, dep_train_file, 1)#call read_data() for train_set

src_dev_file = '/home/alapan/joint_ee/5_10_21/dev_bert.sent'
trg_dev_file = '/home/alapan/joint_ee/5_10_21/dev_bert.pointer'
pos_dev_file = '/home/alapan/joint_ee/5_10_21/dev_bert.pos'
ent_dev_file = '/home/alapan/joint_ee/5_10_21/dev_bert.ent'
dep_dev_file = '/home/alapan/joint_ee/5_10_21/dev_bert.dep'
dev_data = read_data(src_dev_file, trg_dev_file, pos_dev_file, ent_dev_file, dep_dev_file, 2)#call read_data() for dev_set

src_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.sent'
trg_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.pointer'
pos_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.pos'
ent_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.ent'
dep_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.dep'
test_data = read_data(src_test_file, trg_test_file, pos_test_file, ent_test_file, dep_test_file, 3)#call read_data() for dev_set

custom_print('Training data size:', len(train_data))
custom_print('Development data size:', len(dev_data))

custom_print("preparing vocabulary......")
save_vocab = '/home/alapan/joint_ee/vocab.pkl'
custom_print("getting pos tags......")
#print("getting pos tags......")
pos_vocab = build_tags(pos_train_file, pos_dev_file, pos_test_file)
ent_vocab = build_tags(ent_train_file, ent_dev_file, ent_test_file)
dep_vocab = build_tags(dep_train_file, dep_dev_file, dep_test_file)

word_vocab, char_vocab, word_embed_matrix = build_vocab(train_data, dev_data, test_data, save_vocab, embedding_file)#create vocabulary and word embeddings




custom_print("loading word vectors......")
vocab_file_name = '/home/alapan/joint_ee/vocab.pkl'
word_vocab, char_vocab, pos_vocab, ent_vocab, dep_vocab = load_vocab(vocab_file_name)
custom_print('vocab size:', len(word_vocab))
model_file = '/home/alapan/joint_ee/5_10_21/files_23_12/model_bert_13_1.h5py'

best_model = get_model(model_name)
custom_print(best_model)

if torch.cuda.is_available():
    best_model.cuda()
if n_gpu > 1:
    best_model = torch.nn.DataParallel(best_model)
best_model.load_state_dict(torch.load(model_file))

custom_print('\nTest Results\n')
#print('\nTest Results\n')
src_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.sent'
trg_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.pointer'
pos_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.pos'
ent_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.ent'
dep_test_file = '/home/alapan/joint_ee/5_10_21/test_bert.dep'
test_data = read_data(src_test_file, trg_test_file, pos_test_file, ent_test_file, dep_test_file, 3)

sent_reader=open('/home/alapan/joint_ee/5_10_21/test_bert.sent','r')
test_sent_lines = sent_reader.readlines()
sent_reader.close()
custom_print('Test size:', len(test_data))

reader = open(os.path.join('test_trim_oct.tup'))
test_gt_lines = reader.readlines()
reader.close()


test_preds = predict(test_data, best_model, model_name)
pred_pos, gt_pos, correct_pos, ti, tc, ai, ro = get_F1(test_data, test_preds)
custom_print(pred_pos, '\t', gt_pos, '\t', correct_pos)

custom_print('no of correctly identified triggers= '+str(ti))
custom_print('no of correctly classified triggers= '+str(tc))
custom_print('no of correctly identified arguments= '+str(ai))
custom_print('no of correctly identified roles= '+str(ro))

p = float(correct_pos) / (pred_pos + 1e-8)
r = float(correct_pos) / (gt_pos + 1e-8)
test_acc = (2 * p * r) / (p + r + 1e-8)


p_ti = float(ti) / (pred_pos + 1e-8)
r_ti = float(ti) / (gt_pos + 1e-8)
ti_test_acc = (2 * p_ti * r_ti) / (p_ti + r_ti + 1e-8)

p_tc = float(tc) / (pred_pos + 1e-8)
r_tc = float(tc) / (gt_pos + 1e-8)
tc_test_acc = (2 * p_tc * r_tc) / (p_tc + r_tc + 1e-8)

p_ai = float(ai) / (pred_pos + 1e-8)
r_ai = float(ai) / (gt_pos + 1e-8)
ai_test_acc = (2 * p_ai * r_ai) / (p_ai + r_ai + 1e-8)

p_ro = float(ro) / (pred_pos + 1e-8)
r_ro = float(ro) / (gt_pos + 1e-8)
ro_test_acc = (2 * p_ro * r_ro) / (p_ro + r_ro + 1e-8)

custom_print('P_tuple:', round(p, 3))
custom_print('P_ti:', round(p_ti, 3))
custom_print('P_tc:', round(p_tc, 3))
custom_print('P_ai:', round(p_ai, 3))
custom_print('P_ro:', round(p_ro, 3))

custom_print('R_tuple:', round(r, 3))
custom_print('R_ti:', round(r_ti, 3))
custom_print('R_tc:', round(r_tc, 3))
custom_print('R_ai:', round(r_ai, 3))
custom_print('R_ro:', round(r_ro, 3))

custom_print('F1:', round(test_acc, 3))
custom_print('TI F1:', round(ti_test_acc,3))
custom_print('TC F1:', round(tc_test_acc,3))
custom_print('AI F1:', round(ai_test_acc,3))
custom_print('RL F1:', round(ro_test_acc,3))

write_test_res(test_data, test_sent_lines, test_gt_lines, test_preds, 'test_13_1.out')
logger.close()
