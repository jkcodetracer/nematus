'''
Rescoring an n-best list of translations using a translation model.
'''
import sys
import argparse
import tempfile

import numpy
import cPickle as pkl

from data_iterator import TextIterator

from nmt import (pred_probs, load_params, build_model, prepare_data,
    init_params, init_tparams)

from theano.sandbox.rng_mrg import MRG_RandomStreams as RandomStreams
import theano

def rescore_model(source_file, nbest_file, saveto, models, options, b, normalize, verbose):

    trng = RandomStreams(1234)

    fs_log_probs = []

    for model, option in zip(models, options):

        # allocate model parameters
        params = init_params(option)

        # load model parameters and set theano shared variables
        params = load_params(model, params)
        tparams = init_tparams(params)

        trng, use_noise, \
            x, x_mask, y, y_mask, \
            opt_ret, \
            cost = \
            build_model(tparams, option)
        inps = [x, x_mask, y, y_mask]
        use_noise.set_value(0.)

        f_log_probs = theano.function(inps, cost)

        fs_log_probs.append(f_log_probs)

    def _score(pairs):
        # sample given an input sequence and obtain scores
        scores = []
        for i, f_log_probs in enumerate(fs_log_probs):
            scores.append(pred_probs(f_log_probs, prepare_data, options[i], pairs, normalize=normalize))

        return scores

    lines = source_file.readlines()
    nbest_lines = nbest_file.readlines()

    with tempfile.NamedTemporaryFile(prefix='rescore-tmpin') as tmp_in, tempfile.NamedTemporaryFile(prefix='rescore-tmpout') as tmp_out:
        for line in nbest_lines:
            linesplit = line.split(' ||| ')
            idx = int(linesplit[0])
            tmp_in.write(lines[idx])
            tmp_out.write(linesplit[1] + '\n')
        tmp_in.seek(0)
        tmp_out.seek(0)
        pairs = TextIterator(tmp_in.name, tmp_out.name,
                         options[0]['dictionaries'][0], options[0]['dictionaries'][1],
                         n_words_source=options[0]['n_words_src'], n_words_target=options[0]['n_words'],
                         batch_size=b,
                         maxlen=float('inf'),
                         sort_by_length=False) #TODO: sorting by length could be more efficient, but we'd have to synchronize scores with n-best list after

        scores = _score(pairs)
        for i, line in enumerate(nbest_lines):
            score_str = ' '.join(map(str,[s[i] for s in scores]))
            saveto.write('{0} {1}\n'.format(line.strip(), score_str))


def main(models, source_file, nbest_file, saveto, b=80,
         normalize=False, verbose=False):

    # load model model_options
    options = []
    for model in args.models:
        with open('%s.pkl' % model, 'rb') as f:
            options.append(pkl.load(f))
            #hacks for using old models with missing options
            if not 'dropout_embedding' in options[-1]:
                options[-1]['dropout_embedding'] = 0
            if not 'dropout_hidden' in options[-1]:
                options[-1]['dropout_hidden'] = 0

    dictionary, dictionary_target = options[0]['dictionaries']

    # load source dictionary and invert
    with open(dictionary, 'rb') as f:
        word_dict = pkl.load(f)
    word_idict = dict()
    for kk, vv in word_dict.iteritems():
        word_idict[vv] = kk
    word_idict[0] = '<eos>'
    word_idict[1] = 'UNK'

    # load target dictionary and invert
    with open(dictionary_target, 'rb') as f:
        word_dict_trg = pkl.load(f)
    word_idict_trg = dict()
    for kk, vv in word_dict_trg.iteritems():
        word_idict_trg[vv] = kk
    word_idict_trg[0] = '<eos>'
    word_idict_trg[1] = 'UNK'

    rescore_model(source_file, nbest_file, saveto, models, options, b, normalize, verbose)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', type=int, default=80,
                        help="Minibatch size (default: %(default)s))")
    parser.add_argument('-n', action="store_true",
                        help="Normalize scores by sentence length")
    parser.add_argument('-v', action="store_true", help="verbose mode.")
    parser.add_argument('--models', '-m', type=str, nargs = '+', required=True)
    parser.add_argument('--source', '-s', type=argparse.FileType('r'),
                        required=True, metavar='PATH',
                        help="Source text file")
    parser.add_argument('--input', '-i', type=argparse.FileType('r'),
                        default=sys.stdin, metavar='PATH',
                        help="Input n-best list file (default: standard input)")
    parser.add_argument('--output', '-o', type=argparse.FileType('w'),
                        default=sys.stdout, metavar='PATH',
                        help="Output file (default: standard output)")

    args = parser.parse_args()

    main(args.models, args.source, args.input,
         args.output, b=args.b, normalize=args.n, verbose=args.v)