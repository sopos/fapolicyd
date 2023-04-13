%global selinuxtype targeted
%global moduletype contrib
%define semodule_version 0.4

Summary: Application Whitelisting Daemon
Name: fapolicyd
Version: 1.1.5
Release: 1
License: GPLv3+
URL: http://people.redhat.com/sgrubb/fapolicyd
Source0: https://people.redhat.com/sgrubb/fapolicyd/%{name}-%{version}.tar.gz
#Source1: https://github.com/linux-application-whitelisting/% {name}-selinux/releases/download/v% {semodule_version}/% {name}-selinux-% {semodule_version}.tar.gz
# https://github.com/linux-application-whitelisting/fapolicyd-selinux/archive/refs/tags/v0.4.tar.gz#/fapolicyd-selinux-0.4.tar.gz
Source1: https://github.com/linux-application-whitelisting/%{name}-selinux/archive/refs/tags/v%{semodule_version}.tar.gz#/%{name}-selinux-%{semodule_version}.tar.gz
# we bundle uthash for rhel9
Source2: https://github.com/troydhanson/uthash/archive/refs/tags/v2.3.0.tar.gz#/uthash-2.3.0.tar.gz
BuildRequires: gcc
BuildRequires: kernel-headers
BuildRequires: autoconf automake make gcc libtool
BuildRequires: systemd systemd-devel openssl-devel rpm-devel file-devel file
BuildRequires: libcap-ng-devel libseccomp-devel lmdb-devel
BuildRequires: python3-devel

%if 0%{?rhel} == 0
BuildRequires: uthash-devel
%endif

Requires: %{name}-plugin
Recommends: %{name}-selinux
Requires(pre): shadow-utils
Requires(post): systemd-units
Requires(preun): systemd-units
Requires(postun): systemd-units

Patch1: fapolicyd-uthash-bundle.patch
Patch2: fapolicyd-selinux-1.patch
Patch15: fapolicyd-selinux-2.patch

%description
Fapolicyd (File Access Policy Daemon) implements application whitelisting
to decide file access rights. Applications that are known via a reputation
source are allowed access while unknown applications are not. The daemon
makes use of the kernel's fanotify interface to determine file access rights.

%package        selinux
Summary:        Fapolicyd selinux
Group:          Applications/System
Requires:       %{name} = %{version}-%{release}
BuildRequires:  selinux-policy
BuildRequires:  selinux-policy-devel
BuildArch: noarch
%{?selinux_requires}

%description    selinux
The %{name}-selinux package contains selinux policy for the %{name} daemon.

%prep

%setup -q

# selinux
%setup -q -D -T -a 1

%if 0%{?rhel} != 0
# uthash
%setup -q -D -T -a 2
%patch1 -p1 -b .uthash
%endif

%patch2 -p1 -b .selinux1
%patch15 -p1 -b .selinux2


# generate rules for python
sed -i "s|%python2_path%|`readlink -f %{__python2}`|g" rules.d/*.rules
sed -i "s|%python3_path%|`readlink -f %{__python3}`|g" rules.d/*.rules

# Detect run time linker directly from bash
interpret=`readelf -e /usr/bin/bash \
                   | grep Requesting \
                   | sed 's/.$//' \
                   | rev | cut -d" " -f1 \
                   | rev`

sed -i "s|%ld_so_path%|`realpath $interpret`|g" rules.d/*.rules

%build
./autogen.sh
%configure \
    --with-audit \
    --with-rpm \
    --disable-shared

make CFLAGS="%{optflags}" %{?_smp_mflags}

# selinux
pushd %{name}-selinux-%{semodule_version}
make
popd

%check
make check

# selinux
%pre selinux
%selinux_relabel_pre -s %{selinuxtype}

%install
%make_install
install -p -m 644 -D init/%{name}-tmpfiles.conf %{buildroot}/%{_tmpfilesdir}/%{name}.conf
mkdir -p %{buildroot}/%{_localstatedir}/lib/%{name}
mkdir -p %{buildroot}/run/%{name}
mkdir -p %{buildroot}%{_sysconfdir}/%{name}/trust.d
mkdir -p %{buildroot}%{_sysconfdir}/%{name}/rules.d
# get list of file names between known-libs and restrictive from sample-rules/README-rules
cat %{buildroot}/%{_datadir}/%{name}/sample-rules/README-rules \
  | grep -A 100 'known-libs' \
  | grep -B 100 'restrictive' \
  | grep '^[0-9]' > %{buildroot}/%{_datadir}/%{name}/default-ruleset.known-libs
chmod 644 %{buildroot}/%{_datadir}/%{name}/default-ruleset.known-libs

# selinux
install -d %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype}
install -m 0644 %{name}-selinux-%{semodule_version}/%{name}.pp.bz2 %{buildroot}%{_datadir}/selinux/packages/%{selinuxtype}
install -d -p %{buildroot}%{_datadir}/selinux/devel/include/%{moduletype}
install -p -m 644 %{name}-selinux-%{semodule_version}/%{name}.if %{buildroot}%{_datadir}/selinux/devel/include/%{moduletype}/ipp-%{name}.if

#cleanup
find %{buildroot} \( -name '*.la' -o -name '*.a' \) -delete

%define manage_default_rules   default_changed=0 \
  # check changed fapolicyd.rules \
  if [ -e %{_sysconfdir}/%{name}/%{name}.rules ]; then \
    diff %{_sysconfdir}/%{name}/%{name}.rules %{_datadir}/%{name}/%{name}.rules.known-libs >/dev/null 2>&1 || { \
      default_changed=1; \
      #echo "change detected in fapolicyd.rules"; \
      } \
  fi \
  if [ -e %{_sysconfdir}/%{name}/rules.d ]; then \
    default_ruleset='' \
    # get listing of default rule files in known-libs \
    [ -e %{_datadir}/%{name}/default-ruleset.known-libs ] && default_ruleset=`cat %{_datadir}/%{name}/default-ruleset.known-libs` \
    # check for removed or added files \
    default_count=`echo "$default_ruleset" | wc -l` \
    current_count=`ls -1 %{_sysconfdir}/%{name}/rules.d/*.rules | wc -l` \
    [ $default_count -eq $current_count ] || { \
      default_changed=1; \
      #echo "change detected in number of rule files d:$default_count vs c:$current_count"; \
      } \
    for file in %{_sysconfdir}/%{name}/rules.d/*.rules; do \
      if echo "$default_ruleset" | grep -q "`basename $file`"; then \
        # compare content of the rule files \
        diff $file %{_datadir}/%{name}/sample-rules/`basename $file` >/dev/null 2>&1 || { \
          default_changed=1; \
          #echo "change detected in `basename $file`"; \
          } \
      else \
        # added file detected \
        default_changed=1 \
        #echo "change detected in added rules file `basename $file`"; \
      fi \
    done \
  fi \
  # remove files if no change against default rules detected \
  [ $default_changed -eq 0 ] && rm -rf %{_sysconfdir}/%{name}/%{name}.rules %{_sysconfdir}/%{name}/rules.d/* || : \


%pre
getent passwd %{name} >/dev/null || useradd -r -M -d %{_localstatedir}/lib/%{name} -s /sbin/nologin -c "Application Whitelisting Daemon" %{name}
if [ $1 -eq 2 ]; then
# detect changed default rules in case of upgrade
%manage_default_rules
fi

%post
# if no pre-existing rule file
if [ ! -e %{_sysconfdir}/%{name}/%{name}.rules ] ; then
 files=`ls %{_sysconfdir}/%{name}/rules.d/ 2>/dev/null | wc -w`
 # Only if no pre-existing component rules
 if [ "$files" -eq 0 ] ; then
  ## Install the known libs policy
  for rulesfile in `cat %{_datadir}/%{name}/default-ruleset.known-libs`; do
    cp %{_datadir}/%{name}/sample-rules/$rulesfile  %{_sysconfdir}/%{name}/rules.d/
  done
  chgrp %{name} %{_sysconfdir}/%{name}/rules.d/*
  if [ -x /usr/sbin/restorecon ] ; then
   # restore correct label
   /usr/sbin/restorecon -F %{_sysconfdir}/%{name}/rules.d/*
  fi
  fagenrules >/dev/null
 fi
fi
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service
if [ $1 -eq 0 ]; then
# detect changed default rules in case of uninstall
%manage_default_rules
else
  [ -e %{_sysconfdir}/%{name}/%{name}.rules ] && rm -rf %{_sysconfdir}/%{name}/rules.d/* || :
fi

%postun
%systemd_postun_with_restart %{name}.service

%files
%doc README.md
%{!?_licensedir:%global license %%doc}
%license COPYING
%attr(755,root,%{name}) %dir %{_datadir}/%{name}
%attr(755,root,%{name}) %dir %{_datadir}/%{name}/sample-rules
%attr(644,root,%{name}) %{_datadir}/%{name}/default-ruleset.known-libs
%attr(644,root,%{name}) %{_datadir}/%{name}/sample-rules/*
%attr(644,root,%{name}) %{_datadir}/%{name}/fapolicyd-magic.mgc
%attr(750,root,%{name}) %dir %{_sysconfdir}/%{name}
%attr(750,root,%{name}) %dir %{_sysconfdir}/%{name}/trust.d
%attr(750,root,%{name}) %dir %{_sysconfdir}/%{name}/rules.d
%attr(644,root,%{name}) %{_sysconfdir}/bash_completion.d/fapolicyd.bash_completion
%ghost %verify(not md5 size mtime) %attr(644,root,%{name}) %{_sysconfdir}/%{name}/rules.d/*
%ghost %verify(not md5 size mtime) %attr(644,root,%{name}) %{_sysconfdir}/%{name}/%{name}.rules
%config(noreplace) %attr(644,root,%{name}) %{_sysconfdir}/%{name}/%{name}.conf
%config(noreplace) %attr(644,root,%{name}) %{_sysconfdir}/%{name}/rpm-filter.conf
%config(noreplace) %attr(644,root,%{name}) %{_sysconfdir}/%{name}/%{name}.trust
%ghost %attr(644,root,%{name}) %{_sysconfdir}/%{name}/compiled.rules
%attr(644,root,root) %{_unitdir}/%{name}.service
%attr(644,root,root) %{_tmpfilesdir}/%{name}.conf
%attr(755,root,root) %{_sbindir}/%{name}
%attr(755,root,root) %{_sbindir}/%{name}-cli
%attr(755,root,root) %{_sbindir}/fagenrules
%attr(644,root,root) %{_mandir}/man8/*
%attr(644,root,root) %{_mandir}/man5/*
%attr(644,root,root) %{_mandir}/man1/*
%ghost %attr(440,%{name},%{name}) %verify(not md5 size mtime) %{_localstatedir}/log/%{name}-access.log
%attr(770,root,%{name}) %dir %{_localstatedir}/lib/%{name}
%attr(770,root,%{name}) %dir /run/%{name}
%ghost %attr(660,root,%{name}) /run/%{name}/%{name}.fifo
%ghost %attr(660,%{name},%{name}) %verify(not md5 size mtime) %{_localstatedir}/lib/%{name}/data.mdb
%ghost %attr(660,%{name},%{name}) %verify(not md5 size mtime) %{_localstatedir}/lib/%{name}/lock.mdb


%files selinux
%{_datadir}/selinux/packages/%{selinuxtype}/%{name}.pp.bz2
%ghost %verify(not md5 size mode mtime) %{_sharedstatedir}/selinux/%{selinuxtype}/active/modules/200/%{name}
%{_datadir}/selinux/devel/include/%{moduletype}/ipp-%{name}.if

%post selinux
%selinux_modules_install -s %{selinuxtype} %{_datadir}/selinux/packages/%{selinuxtype}/%{name}.pp.bz2
%selinux_relabel_post -s %{selinuxtype}

%postun selinux
if [ $1 -eq 0 ]; then
    %selinux_modules_uninstall -s %{selinuxtype} %{name}
fi

%posttrans selinux
%selinux_relabel_post -s %{selinuxtype}

%changelog
* Tue Aug 16 2022 Steve Grubb <sgrubb@redhat.com> 1.1.5-1
- New release
