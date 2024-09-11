//  This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
//  Copyright (c) 2024 Kendall Goto.
//
//  This program is free software: you can redistribute it and/or modify
//  it under the terms of the GNU General Public License as published by
//  the Free Software Foundation, version 3.
//
//  This program is distributed in the hope that it will be useful, but
//  WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
//  General Public License for more details.
//
//  You should have received a copy of the GNU General Public License
//  along with this program. If not, see <http://www.gnu.org/licenses/>.

package setup

import (
	"archive/tar"
	"bufio"
	"bytes"
	"compress/gzip"
	"crypto/sha1"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path"
	"strconv"
	"strings"

	"github.com/kendallgoto/ilo4_unlock/pkg/config"
	"github.com/urfave/cli/v2"
)

func setup(cCtx *cli.Context) error {
	fmt.Println("Downloading binaries ...")
	workingDir := cCtx.String("workdir")
	err := os.MkdirAll(workingDir, 0744)
	if err != nil {
		return err
	}
	for name, patch := range config.Patches {
		if name == "default" {
			continue
		}
		binaryPath := path.Join(workingDir, patch.BinaryInfo.Name)
		fmt.Printf("Downloading %s to %s\n", name, binaryPath)
		file, err := os.OpenFile(binaryPath, os.O_RDWR|os.O_CREATE|os.O_EXCL, 0644)
		if err != nil {
			if !errors.Is(err, fs.ErrExist) {
				return err
			}
			fmt.Println("Binary already exists, not downloading ...")
			file, err = os.OpenFile(binaryPath, os.O_RDONLY, 0644)
			if err != nil {
				return err
			}
			defer file.Close()
		} else {
			defer file.Close()
			fmt.Printf("Downloading %s\n", &patch.BinaryInfo.Url)
			resp, err := http.Get(patch.BinaryInfo.Url.String())
			if err != nil {
				return err
			}
			defer resp.Body.Close()
			scanner := bufio.NewScanner(resp.Body)
			tinybuf := make([]byte, 4096)
			scanner.Buffer(tinybuf, 4096)
			lim := 20 // read the first 20 lines to find the _SKIP marker
			for i := 0; i < lim; i++ {
				if !scanner.Scan() {
					return fmt.Errorf("unexpected EOF during binary csexe read")
				}
				if lim != 20 {
					continue
				}
				line := scanner.Text()
				if strings.Contains(line, "_SKIP=") {
					lim, err = strconv.Atoi(strings.TrimPrefix(line, "_SKIP="))
					if err != nil {
						return err
					}
					lim--
				}
			}
			pipedReader, pipedWriter := io.Pipe()
			go func() {
				defer pipedWriter.Close()
				// we probably ran past in the scanner
				// so read back the buffer to find the part we missed
				indx := bytes.Index(tinybuf, []byte{0x1f, 0x8b})
				if indx < 0 {
					fmt.Println("failed to find gzip segment of csexe")
					return
				}
				pipedWriter.Write(tinybuf[indx:])
				// then just copy the rest as-is
				io.Copy(pipedWriter, resp.Body)
			}()
			gz, err := gzip.NewReader(pipedReader)
			if err != nil {
				return err
			}
			tarz := tar.NewReader(gz)
			wroteFile := false
			for !wroteFile {
				header, err := tarz.Next()
				if err == io.EOF {
					break
				} else if err != nil {
					return err
				}
				if strings.Contains(header.Name, ".bin") {
					_, err = io.Copy(file, tarz)
					wroteFile = true
				}
			}
			if !wroteFile {
				return fmt.Errorf("failed to get bin for %s", name)
			}
		}
		file.Sync()
		file.Seek(0, io.SeekStart)
		hash := sha1.New()
		io.Copy(hash, file)
		if digest := hash.Sum(nil); !bytes.Equal(digest, patch.Checksums.Binary) {
			file.Close()
			os.Remove(binaryPath)
			return fmt.Errorf("got bad checksum for downloaded file (got %x, expected %x)", digest, patch.Checksums.Binary)
		}
		fmt.Printf("Downloaded and verified %s\n", binaryPath)
	}
	return nil
}

func Command() *cli.Command {
	return &cli.Command{
		Name:   "setup",
		Usage:  "setup necessary runtime resources",
		Action: setup,
	}
}
