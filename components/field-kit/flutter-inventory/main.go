// Read package class names and their declaring Dart library from an AOT snapshot.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sort"
	"strings"
	"syscall"
	"unsafe"

	"aotopsy/internal/cluster"
	"aotopsy/internal/dartfmt"
	"aotopsy/internal/elfx"
	"aotopsy/internal/snapshot"
)

type row struct {
	ClassID int32  `json:"class_id"`
	Name    string `json:"class_name"`
	Library string `json:"library_uri"`
}

// This executable is shipped for Windows x64. Place the parser in a private
// memory-limited job before it reads data-dependent object counts.
func limitMemory() error {
	k := syscall.NewLazyDLL("kernel32.dll")
	job, _, err := k.NewProc("CreateJobObjectW").Call(0, 0)
	if job == 0 {
		return err
	}
	// JOBOBJECT_EXTENDED_LIMIT_INFORMATION, Windows x64 ABI.
	var info [144]byte
	*(*uint32)(unsafe.Pointer(&info[16])) = 0x100 // JOB_OBJECT_LIMIT_PROCESS_MEMORY
	*(*uintptr)(unsafe.Pointer(&info[112])) = 256 << 20
	ok, _, err := k.NewProc("SetInformationJobObject").Call(job, 9, uintptr(unsafe.Pointer(&info[0])), uintptr(len(info)))
	if ok == 0 {
		return err
	}
	proc, _, _ := k.NewProc("GetCurrentProcess").Call()
	ok, _, err = k.NewProc("AssignProcessToJobObject").Call(job, proc)
	if ok == 0 {
		return err
	}
	return nil
}

func inventory(path string) ([]row, error) {
	stat, err := os.Stat(path)
	if err != nil || !stat.Mode().IsRegular() || stat.Size() < 64 || stat.Size() > 16<<20 {
		return nil, errors.New("expected an ordinary library of at most 16 MiB")
	}
	file, err := elfx.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	if !file.IsARM64() {
		return nil, errors.New("expected an ARM64 ELF library")
	}
	options := dartfmt.Options{Mode: dartfmt.ModeStrict, MaxSteps: 2000000}
	info, err := snapshot.Extract(file, options)
	if err != nil {
		return nil, err
	}
	if info.Version == nil || !info.Version.Supported || info.IsolateHeader == nil {
		return nil, errors.New("unrecognized snapshot")
	}
	data := info.IsolateData.Data
	start, err := snapshot.FindClusterDataStart(data)
	if err != nil {
		return nil, err
	}
	result, err := cluster.ScanClusters(data, start, info.Version, false, options)
	if err != nil {
		return nil, err
	}
	if err := cluster.ReadFill(data, result, info.Version, false, info.IsolateHeader.TotalSize); err != nil {
		return nil, err
	}
	names := make(map[int]string)
	for _, s := range result.Strings {
		names[s.RefID] = s.Value
	}
	libraries := make(map[int]string)
	for _, obj := range result.Named {
		if obj.CID == info.Version.CIDs.Library {
			uri := names[obj.NameRefID]
			if strings.HasPrefix(uri, "package:") && len(uri) <= 512 {
				libraries[obj.RefID] = uri
			}
		}
	}
	rows := []row{}
	for _, c := range result.Classes {
		uri, ok := libraries[c.LibraryRefID]
		name := names[c.NameRefID]
		if ok && name != "" && len(name) <= 256 {
			rows = append(rows, row{c.ClassID, name, uri})
			if len(rows) > 8192 {
				return nil, errors.New("package class inventory exceeds its limit")
			}
		}
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Library != rows[j].Library {
			return rows[i].Library < rows[j].Library
		}
		return rows[i].ClassID < rows[j].ClassID
	})
	return rows, nil
}

func main() {
	if len(os.Args) != 2 {
		os.Exit(2)
	}
	if limitMemory() != nil {
		os.Exit(1)
	}
	rows, err := inventory(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(rows); err != nil {
		os.Exit(1)
	}
}
