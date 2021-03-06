'''
See arxiv:1410.3365, "Efficient and robust analysis of complex scattering data under noise in microwave resonators."

Jason Stevens
'''

from numpy import *;
import scipy.optimize as opt;
import matplotlib.pyplot as plt;
from numpy.linalg import eig,inv;
import sys;
import os;
import fnmatch;

#tau = 6.0e-6 #This is the cable delay, and I measured it based on our setup.
tau = 7.0e-8;
#tau = 0.;

taudatas = [];

#Doesn't really return despiked data, but uses despiked data to find min and max indexes.
#Despikes by taking some number of points surrounding the point being considered,
#Taking the mean and standard deviation of those points, and finding if the considered point
#is more than 4 standard deviations from the mean. If so, this point is ignored for the purposes of
#finding the min/max, since it is just some noise spike.
def despike(datax, datay):
    size = 30;
    xs = [];
    ys = [];
    stds = [];
    minvalue = None;
    maxvalue = None;
    minidx = None;
    maxidx = None;
    for i in range(size, len(datax)-size):
        xs.append(datax[i]);
        ys.append(mean(datay[i-size:i+size]));
        stds.append(std(datay[i-size:i+size]));
        if abs(ys[-1]-datay[i])<=2*stds[-1]:
            if minvalue==None or datay[i]<minvalue:
                minvalue = datay[i];
                minidx = i;
            if maxvalue==None or datay[i]>maxvalue:
                maxvalue = datay[i];
                maxidx = i;
    return minidx,maxidx;
    '''
    plt.plot(datax,datay);
    plt.plot(xs,ys);
    plt.plot(xs, [y+4*s for y,s in zip(ys,stds)]);
    plt.plot(xs, [y-4*s for y,s in zip(ys,stds)]);
    plt.show();
    plt.clf();
    '''

#A simple low pass filter.
def lowpass(data, a):
    output = data[:];
    output[0] = a*data[0];
    for i in range(1,len(data)):
        output[i] = a*data[i] + (1.0-a)*output[i-1];
    return output;

#Algebraic fit of the points x,y to a circle.
def fitCircle(x,y):
    #Modified from http://nicky.vanforeest.com/misc/fitEllipse/fitEllipse.html
    #Changed C and D to match the arxiv paper at top for circle fits.
    #Otherwise the algorithm is identical.
    x = x[:,newaxis];
    y = y[:,newaxis];
    D = hstack((x*x+y*y,x,y,ones_like(x)));
    S = dot(D.T,D);
    C = zeros([4,4]);
    C[0,3] = C[3,0] = -2.0; C[1,1] = C[2,2] = 1.0;
    E, V = eig(dot(inv(S), C));
    n = argmax(abs(E));
    a = V[:,n];

    x0 = -a[1]/(2.0*a[0]);
    y0 = -a[2]/(2.0*a[0]);
    r = (a[1]**2+a[2]**2-4*a[0]*a[3])**0.5/(2.0*abs(a[0]));
    #print a, a[1]**2+a[2]**2-4*a[0]*a[3];
    return (x0,y0,r);

#Calculate goodness of fit to a circle fit.
def chisq2(xs, ys, x0, y0, r):
    s = 0.0;
    for x,y in zip(xs,ys):
        s += r**2 - (x-x0)**2 - (y-y0)**2;
    return s;
#Wrapper for the above, that fits a circle first and then calculates
# how well the points fit to that circle.
def chisq(zs):
    xs = real(zs);
    ys = imag(zs);
    (x0,y0,r) = fitCircle(xs,ys);
    return chisq2(xs,ys,x0,y0,r);

#Actually finds resonator frequency.
#Later, will make a version that returns the Qs too.
def fitDataRes0(filename,tau=None):
    #Get all the data
    f = open(filename);
    freqs = [];
    mag = [];
    phase = [];
    for l in f:
        a = l.split();
        freqs.append(float(a[0]));
        #mag.append(float(a[1]));
        mag.append(10.**(float(a[1])/20.));
        phase.append(float(a[2])*pi/180.);
    f.close();

    #Process phase information, including finding bandwidth and frequency guesses.
    f0idx = argmin(mag);
    f0 = freqs[f0idx];
    phase = unwrap(phase);
    #maxphaseidx = argmax(phase);
    #minphaseidx = argmin(phase);
    minphaseidx, maxphaseidx = despike(freqs,phase);
    if minphaseidx>maxphaseidx:
        temp = minphaseidx;
        minphaseidx = maxphaseidx;
        maxphaseidx = temp;
        
    xs = [r*cos(phi) for r,phi in zip(mag,phase)];
    ys = [r*sin(phi) for r,phi in zip(mag,phase)];
    zs = [x + 1j*y for x,y in zip(xs,ys)];

    freqs2 = [x for x in freqs];
    freqs = freqs[minphaseidx:maxphaseidx];
    zs = zs[minphaseidx:maxphaseidx];
    
    #Search for the cable delay tau.
    if tau==None:
        taus = linspace(0.0,1e-5,50);
        fits = [chisq([z*exp(2.*pi*1j*t*f) for z,f in zip(zs,freqs)]) for t in taus];

        taudatas.append(fits);

        #Find the cable delay tau. Most of the time this works very well.
        #Occasionally, it does not. I'll have to search for cases where it doesn't later.
        quadfit = polyfit(taus,fits,4);
        octfit = polyfit(taus,fits,8);
        #dpdx = array([4*quadfit[0],3*quadfit[1],2*quadfit[2],quadfit[3]]);
        dpdx = array([8*octfit[0],7*octfit[1],6*octfit[2],5*octfit[3],4*octfit[4],3*octfit[5],2*octfit[6],octfit[7]]);
        quadroots = roots(dpdx);
        quadroots = quadroots[(quadroots >= 0.0) & (quadroots <= 1e-5) & (quadroots == real(quadroots))];
        quadrootvals = [polyval(octfit,x) for x in quadroots];
        #print quadroots;
        #print quadrootvals;
        tau = quadroots[argmin(quadrootvals)];
        if tau<0: tau=0;
        print "Cable delay is "+str(real(tau*1e9))+" nS";

        #Plot the fit to see how well it worked.
        '''
        plt.plot(taus,fits);
        plt.plot(taus,[polyval(octfit,t) for t in taus]);
        plt.plot([tau],[polyval(octfit,tau)],'o');
        plt.show();
        plt.clf();
        '''

    #Plot the circle fit with the cable delay taken into account.
    zs2 = [z*exp(2.*pi*1j*tau*f) for z,f in zip(zs,freqs)];
    #plt.plot(real(zs2),imag(zs2));
    (x0,y0,r) = fitCircle(real(zs2),imag(zs2));
    #plt.plot([x0+r*cos(t) for t in linspace(0,2*pi,100)],[y0+r*sin(t) for t in linspace(0,2*pi,100)]);
    #plt.show();
    #plt.clf();

    #Translate the circle to the origin and fit the phase.
    def fitmodel(f, f0, theta0, Q):
        return theta0 + 2*arctan(2*Q*(1-f/f0));
    xs2 = real(zs2); ys2 = imag(zs2);
    xs2 = [x-x0 for x in xs2];
    ys2 = [y-y0 for y in ys2];
    zs2 = [x + 1j*y for x,y in zip(xs2,ys2)];

    Qguess = -mean(freqs)/(freqs[-1]-freqs[0]);
    #params, cov = opt.curve_fit(fitmodel, freqs[int(len(freqs)*0.2):int(len(freqs)*0.8)], angle(zs)[int(len(freqs)*0.2):int(len(freqs)*0.8)], [f0,mean(angle(zs)),Qguess]);
    try:
        params, cov = opt.curve_fit(fitmodel, freqs, unwrap(angle(zs2)), [f0,mean(angle(zs2)),Qguess]);
    except RuntimeError:
        #plt.plot(xs2,ys2);
        #plt.show();
        #plt.clf();
        return freqs2[argmin(mag)],tau;
    #plt.plot(freqs, unwrap(angle(zs2)));
    #plt.plot(freqs, [fitmodel(f,params[0],params[1],params[2]) for f in freqs]);
    #plt.show();
    #plt.clf();

    #plt.plot(freqs, mag[minphaseidx:maxphaseidx]);
    #plt.plot([params[0]],[min(mag)],"o");
    #plt.plot([freqs[argmin(mag[minphaseidx:maxphaseidx])]],[min(mag)],"x");
    #plt.show();
    #plt.clf();

    return params[0], tau;

###################### MAIN ######################

#Make sure the user passed a data file
if len(sys.argv)<2:
    print "Pass data";
    exit();
datadir = sys.argv[1];

f0, tau = fitDataRes0(sys.argv[1], tau); #This returns tau in case you want it to find tau, but you don't.
					#Since you passed it a value, it will just use that tau.

print f0;
