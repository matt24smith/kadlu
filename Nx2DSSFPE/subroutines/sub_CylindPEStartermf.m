function [psi] = sub_CylindPEStartermf(k0,kz,Starter,zs)

% use global variables declared before
global Z

nk0=length(k0);
nZ=length(Z(:,1));

% the following three starters simulates point source
switch lower(Starter.type(1:2));
    case 'ga'
        %(1) Gaussian starter
        psi = sqrt(k0(ones(1,nZ),:)) .* exp( -0.5*(Z(:,1)-zs).^2*k0.^2 ); 
        psi = psi - ( sqrt(k0(ones(1,nZ),:)) .* exp( -0.5*(Z(:,1)+zs).^2*k0.^2  ));
        psi = fft(psi);
    case 'gr'
        %(2) Greene's starter 
        psi = sqrt(k0(ones(1,nZ),:)) .* (1.4467-.04201*(Z(:,1)-zs).^2*k0.^2) .*exp(-((Z(:,1)-zs).^2)/3.0512*k0.^2);
        psi = psi - ( sqrt(k0(ones(1,nZ),:)) .* (1.4467-.04201*(Z(:,1)+zs).^2*k0.^2) .*exp(-((Z(:,1)+zs).^2)/3.0512*k0.^2) ); %   d1 and d2 are distances already squared....
        psi = fft(psi);
    case 'th'
        %(3) Thomson's starter
        psi = exp(-1i*pi/4)*2*sqrt(2*pi)*sin(kz(:,ones(nk0,1)))./sqrt( sqrt(k0(ones(1,nZ),:).^2 - kz(:,ones(nk0,1)).^2));
        % normalize the starter
        psi = psi/(Z(2,1)-Z(1,1));
        psi(size(Z,1)/2+1,:) = 0; 
        % taper the spectrum to obtain desired angle using Turkey window
        kcut1 = k0*sin(Starter.aperature/180*pi); kcut0 = k0*sin((Starter.aperature-1.5)/180*pi);
        W = .5*(1+cos(pi./(kcut1(ones(1,nZ),:))-kcut0(ones(1,nZ),:))).*(abs(kz(:,ones(1,nk0)) - kcut0(ones(1,nZ),:)) );
        
        W(abs(kz(:,ones(1,nk0)))>=kcut1(ones(1,nZ),:)) = 0; 
        W(abs(kz(:,ones(1,nk0)))<=kcut0(ones(1,nZ),:)) = 1;
        
        psi = psi.*W;
        psi(abs(kz(:,ones(1,nk0)))>=kcut1(ones(1,nZ),:)) = 0;
end

return