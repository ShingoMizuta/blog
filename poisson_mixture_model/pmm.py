import numpy as np
from numpy import log, dot
from scipy import stats
from scipy.special import digamma as psi, gammaln
from scipy.misc import logsumexp
from pandas import DataFrame, concat
import matplotlib.pyplot as plt
import seaborn as sns
sns.set_style('whitegrid')
%matplotlib inline


class PMM(object):
    """ Poisson mixture model """
    def __init__(self, k, d, n, alpha, s, r):
        self.K = k  # number of classes
        self.D = d  # dimension of data
        self.N = n  # number of samples
        self.ALPHA = np.array(alpha)  # parameter of prior Dirichlet dist.
        self.S = s  # shape parameter of  prior Gamma dist.
        self.R = r  # rate parameter of prior Gamma dist.
        self.data_stack = DataFrame()  # dataframe storing generated samples
        self.lamb = np.array([])  # lambda parameter used to generate samples
        self.pi = np.array([])  # pi parameter used to generate samples

    def _sampling(self):
        pi = stats.dirichlet.rvs(self.ALPHA)[0]
        lam = stats.gamma.rvs(self.S, scale=1./self.R, size=self.K*self.D
                              ).reshape((self.K, self.D))
        if not list(self.pi):  # first iteration
            self.pi = pi
            self.lamb = lam
        else:
            self.pi = np.vstack((self.pi, pi))
            self.lamb = np.vstack((self.lamb, lam))
        result = []
        for _ in range(self.N):
            z = stats.rv_discrete(values=(list(range(len(pi))), pi)).rvs()
            x1 = stats.poisson.rvs(lam[int(z)][0])
            x2 = stats.poisson.rvs(lam[int(z)][1])
            result.append([x1, x2, z])
        return DataFrame(result, columns=['x1', 'x2', 'z'])

    def add_samples(self, n_iter):
        n_trials = int(self.data_stack.shape[0] / float(self.N))
        for i in range(n_iter):
            data = self._sampling()
            data['trial'] = i + n_trials
            self.data_stack = self.data_stack.append(data)

    def pick_sample(self, trial):
        return self.data_stack[self.data_stack['trial'] == trial
                               ].drop('trial', axis=1)

    def describe_sample(self, trial):
        header = 'summary of the sample {}'.format(trial)
        print(header, '\n' + '-' * len(header))
        print(self.pick_sample(trial).groupby('z')['x1'].count())
        header = '\nparameters used to generate sample #{}'.format(trial)
        print(header, '\n' + '-' * len(header))
        print('K:', self.K)
        print('D:', self.D)
        print('N:', self.N)
        print('alpha:', self.ALPHA)
        print('s:', self.S)
        print('r:', self.R)
        print('lambda:', self.lamb[trial])
        print('pi:', self.pi[trial])

    def show_samples(self, data=None):
        # http://seaborn.pydata.org/generated/seaborn.FacetGrid.html
        if data is None:
            data = self.data_stack
            col_wrap = 5
        else:
            col_wrap = None
        g = sns.FacetGrid(data, col='trial', hue='z', col_wrap=col_wrap)
        g.map(plt.scatter, 'x1', 'x2').add_legend()
        plt.show()

    def fit(self, X, init_pi, init_r, init_s, init_alpha, n_iter):
        self.pi_inf = np.array([np.array(init_pi)])
        self.r_inf = np.array([np.array(init_r)])
        self.s_inf = np.array([np.array(init_s)])
        self.alpha_inf = np.array([np.array(init_alpha)])
        for _ in range(n_iter):
            r_old = self.r_inf[-1]
            s_old = self.s_inf[-1]
            alpha_old = self.alpha_inf[-1]
            ln_pi_new = [dot(X, psi(s_old[k]) - log(r_old[k])) -
                         (s_old[k] / r_old[k]).sum() +
                         psi(alpha_old[k]) - psi(alpha_old.sum())
                         for k in range(self.K)]
            pi_new = np.exp(np.vstack(ln_pi_new) -
                            logsumexp(ln_pi_new, axis=0)).T
            s_new = dot(pi_new.T, X) + init_s
            n_new = pi_new.sum(axis=0)
            r_new = n_new + init_r
            alpha_new = n_new + init_alpha
            self.pi_inf = np.append(self.pi_inf, [pi_new], axis=0)
            self.r_inf = np.append(self.r_inf, [r_new], axis=0)
            self.s_inf = np.append(self.s_inf, [s_new], axis=0)
            self.alpha_inf = np.append(self.alpha_inf, [alpha_new], axis=0)

    def predict(self, trial, init_pi, init_r, init_s, init_alpha, n_iter):
        X_original = self.pick_sample(trial)
        X_inferred = X_original.copy()
        X_original['trial'] = 'original'
        X_inferred['trial'] = 'inferred'
        self.fit(X_inferred[['x1', 'x2']].values, init_pi, init_r, init_s,
                 init_alpha, n_iter)
        X_inferred['z'] = np.argmax(self.pi_inf[-1], axis=1)
        self.show_samples(data=concat([X_original, X_inferred]))

    def kl_divergence(self, init_pi=None, init_r=None, init_s=None,
                      init_alpha=None, n_iter=None, n_trials=None):
        if ((init_pi is None) or (init_r is None) or (init_s is None) or
                (init_alpha is None) or (n_iter is None) or (n_trials is None)):
            init_pi = self.pi_inf[0]
            init_r = self.r_inf[0]
            init_s = self.s_inf[0]
            init_alpha = self.alpha_inf[0]
            n_iter = self.pi_inf.shape[0] - 1
            n_trials = int(self.data_stack.shape[0] / float(self.N))
        kl = []
        for trial in range(n_trials):
            X = self.pick_sample(trial)[['x1', 'x2']].values
            self.fit(X, init_pi, init_r, init_s, init_alpha, n_iter)
            kl.append([self._kl(X, i) for i in range(n_iter)])
        kl = DataFrame(np.array(kl).T, columns=list(map(str, range(n_trials))))
        return kl

    def _kl(self, X, i):
        pi = self.pi_inf[i]
        s = self.s_inf[i]
        r = self.r_inf[i]
        alpha = self.alpha_inf[i]
        s_ord = self.S
        r_ord = self.R
        alpha_ord = self.ALPHA

        kl1 = -dot(pi.T, dot(X, psi(s).T)).trace() + dot(X.T, dot(pi, log(r))).sum()
        kl1 += np.sum(pi.sum(axis=0) * s.sum(axis=1) / r)
        # use gammaln instead of log(factorial) to avoid overflow
        kl1 += dot(pi.T, gammaln(X + 1)).sum()
        kl2 = dot(pi, log(pi).T).trace() - dot(pi, psi(alpha) - psi(alpha.sum())).sum()
        kl3 = self.D * s_ord * (log(r) - log(r_ord)).sum()
        kl3 += dot(s - s_ord, psi(s).T).trace()
        kl3 += dot(r_ord / r - 1, s.sum(axis=1))
        kl3 += (gammaln(s_ord) - gammaln(s)).sum()
        kl4 = gammaln(alpha.sum()) - gammaln(alpha).sum()
        kl4 += -gammaln(alpha_ord.sum()) + gammaln(alpha_ord).sum()
        kl4 += dot(alpha - alpha_ord, psi(alpha) - psi(alpha.sum()))

        return kl1 + kl2 + kl3 + kl4
